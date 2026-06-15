"""Integration tests for full-margin mode (margin_mode == "full").

These exercise the full BacktestRunner end-to-end with the MarginAccountManager
wired into the position lifecycle. They guard against the regression where
full-margin mode silently discarded realized P&L and double-counted the entry
cost (reconciliation_error == initial_cash).
"""

import pandas as pd

from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.backtest_runner import BacktestRunner


class _OneShotLong(TradingStrategy):
    """Enter long on the first flat bar, then hold until liquidated."""

    def __init__(self) -> None:
        self._emitted = False

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="full_margin_one_shot",
            variant=DataMode.REAL,
            description="One long entry, no exit signal.",
            required_indicators=[],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        if not self._emitted and float(position.get("size", 0) or 0) == 0:
            self._emitted = True
            return SignalResult(
                action="buy",
                direction="long",
                confidence=1.0,
                stop_price=0.0,
                target_price=0.0,
            )
        return SignalResult(action="hold")

    def on_reset(self) -> None:
        self._emitted = False


class _EnterThenExitLong(TradingStrategy):
    """Enter long once, then emit an exit signal while the backtest continues."""

    def __init__(self) -> None:
        self._bars_seen = 0

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="full_margin_enter_then_exit",
            variant=DataMode.REAL,
            description="Enter and exit a long position mid-backtest.",
            required_indicators=[],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        self._bars_seen += 1
        if self._bars_seen == 1 and float(position.get("size", 0) or 0) == 0:
            return SignalResult(action="buy", direction="long", confidence=1.0)
        if self._bars_seen == 3 and float(position.get("size", 0) or 0) != 0:
            return SignalResult(action="sell", direction="exit", confidence=1.0)
        return SignalResult(action="hold")

    def on_reset(self) -> None:
        self._bars_seen = 0


def _rising_bars(n: int = 6) -> pd.DataFrame:
    closes = [100 + i * 10 for i in range(n)]
    return pd.DataFrame(
        {
            "open": [closes[0]] + closes[1:],
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1000] * n,
        },
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )


def _flat_bars(n: int = 6) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100] * n,
            "high": [101] * n,
            "low": [99] * n,
            "close": [100] * n,
            "volume": [1000] * n,
        },
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )


class TestFullMarginReconciliation:
    def test_full_margin_mid_backtest_exit_does_not_double_principal(self):
        """A flat round trip closed before the final bar must not double equity."""
        result = BacktestRunner().run(
            _flat_bars(),
            _EnterThenExitLong(),
            initial_cash=10000,
            interval="1d",
            margin_mode="full",
            enable_funding=False,
        )
        assert result["total_trades"] == 1
        assert result["final_value"] == 10000.0
        assert result["cash"] == 10000.0
        assert result["reconciliation_error"] == 0.0

    def test_full_margin_reconciles_to_zero_without_funding(self):
        """Full-margin mode must keep the accounting identity
        final_value == initial_cash + realized_pnl (reconciliation_error == 0).

        Previously the entry cost was never deducted from the margin account,
        inflating final_value by exactly initial_cash.
        """
        result = BacktestRunner().run(
            _rising_bars(),
            _OneShotLong(),
            initial_cash=10000,
            interval="1d",
            margin_mode="full",
            enable_funding=False,
        )
        assert result["total_trades"] == 1
        assert result["reconciliation_error"] == 0.0

    def test_full_margin_matches_simplified_without_funding(self):
        """With no funding and no margin call, full and simplified modes must
        produce identical equity (same cash flows, just routed through the
        margin account)."""
        runner = BacktestRunner()
        bars = _rising_bars()
        simplified = runner.run(
            bars,
            _OneShotLong(),
            initial_cash=10000,
            interval="1d",
            margin_mode="simplified",
        )
        full = runner.run(
            bars,
            _OneShotLong(),
            initial_cash=10000,
            interval="1d",
            margin_mode="full",
        )
        assert full["final_value"] == simplified["final_value"]
        assert full["cash"] == simplified["cash"]
        assert full["total_trades"] == simplified["total_trades"]
        assert full["reconciliation_error"] == 0.0

    def test_funding_longs_reduces_equity_and_still_reconciles(self):
        """Funding is a per-bar cash drain not present in realized_pnl.
        Longs must pay funding (final_value drops) and the reconciliation
        must still be zero once total_funding is accounted for."""
        runner = BacktestRunner()
        bars = _rising_bars()
        no_funding = runner.run(
            bars,
            _OneShotLong(),
            initial_cash=10000,
            interval="1d",
            margin_mode="full",
            enable_funding=False,
            funding_rate=0.0,
        )
        with_funding = runner.run(
            bars,
            _OneShotLong(),
            initial_cash=10000,
            interval="1d",
            margin_mode="full",
            enable_funding=True,
            funding_rate=0.01,
        )
        # Longs pay funding -> lower final value.
        assert with_funding["final_value"] < no_funding["final_value"]
        # Funding paid is surfaced and positive for a long.
        assert with_funding["total_funding"] > 0
        # Reconciliation accounts for funding.
        assert with_funding["reconciliation_error"] == 0.0

    def test_full_margin_short_reconciles(self):
        """Short entries route through credit_entry_short + settle_exit and
        must also reconcile."""

        class _OneShotShort(TradingStrategy):
            def __init__(self) -> None:
                self._emitted = False

            def meta(self) -> StrategyMeta:
                return StrategyMeta(
                    name="full_margin_short",
                    variant=DataMode.REAL,
                    description="One short entry.",
                    required_indicators=[],
                )

            def on_bar(self, bar: dict, position: dict) -> SignalResult:
                if not self._emitted and float(position.get("size", 0) or 0) == 0:
                    self._emitted = True
                    return SignalResult(
                        action="sell",
                        direction="short",
                        confidence=1.0,
                        stop_price=0.0,
                        target_price=0.0,
                    )
                return SignalResult(action="hold")

            def on_reset(self) -> None:
                self._emitted = False

        result = BacktestRunner().run(
            _rising_bars(),
            _OneShotShort(),
            initial_cash=10000,
            interval="1d",
            margin_mode="full",
            enable_funding=False,
        )
        assert result["total_trades"] == 1
        assert result["reconciliation_error"] == 0.0
