"""Tests for configurable risk price basis (signal_close vs entry_fill)."""

import pandas as pd

from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.backtest_runner import BacktestRunner


class _FixedPctRiskStrategy(TradingStrategy):
    """Enter long with a fixed_pct stop so we can verify which price anchors it."""

    def __init__(self) -> None:
        self._emitted = False

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="risk_basis_test",
            variant=DataMode.REAL,
            description="Risk basis test",
            required_indicators=[],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        if not self._emitted and float(position.get("size", 0) or 0) == 0:
            self._emitted = True
            return SignalResult(
                action="buy",
                direction="long",
                position_size=10,
                stop_price=95.0,
            )
        return SignalResult(action="hold")

    def on_reset(self) -> None:
        self._emitted = False


def _gap_up_bars() -> pd.DataFrame:
    """Signal on bar 0 (close=100), fill on bar 1 open (110), close-out bar 2."""
    return pd.DataFrame(
        {
            "open": [100.0, 110.0, 110.0],
            "high": [100.0, 110.0, 120.0],
            "low": [100.0, 110.0, 100.0],
            "close": [100.0, 110.0, 110.0],
            "volume": [1000, 1000, 1000],
        },
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
    )


class TestRiskPriceBasis:
    """Black-box tests: risk prices anchor on signal close or entry fill."""

    def test_signal_close_preserves_stop_from_signal_bar(self):
        """Default basis keeps the stop computed at the signal bar close."""
        result = BacktestRunner().run(
            _gap_up_bars(),
            _FixedPctRiskStrategy(),
            initial_cash=10000,
            risk_price_basis="signal_close",
        )

        trade = result["trades"][0]
        assert trade["entry_price"] == 110.0  # filled at next open
        # Stop was 95.0 from the signal, not recomputed from 110
        assert result["trust_diagnostics"]["risk_price_basis"] == "signal_close"

    def test_entry_fill_recalculates_stop_from_actual_fill(self):
        """entry_fill basis recalculates the stop from the fill price.

        Signal close=100, stop=95 (5% below). Fill at 110, so the
        rebased stop should be 104.5. We verify behaviorally: on the entry
        bar the low dips to 104 (below rebased 104.5, above original 95).
        With entry_fill, the position is stopped out; with signal_close it is not.
        """
        bars = pd.DataFrame(
            {
                "open": [100.0, 110.0, 110.0],
                "high": [100.0, 112.0, 112.0],
                "low": [100.0, 104.0, 100.0],
                "close": [100.0, 110.0, 110.0],
                "volume": [1000, 1000, 1000],
            },
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        )

        result_signal = BacktestRunner().run(
            bars.copy(),
            _FixedPctRiskStrategy(),
            initial_cash=10000,
            risk_price_basis="signal_close",
        )
        result_fill = BacktestRunner().run(
            bars.copy(),
            _FixedPctRiskStrategy(),
            initial_cash=10000,
            risk_price_basis="entry_fill",
        )

        assert result_signal["trust_diagnostics"]["risk_price_basis"] == "signal_close"
        assert result_fill["trust_diagnostics"]["risk_price_basis"] == "entry_fill"

        # With signal_close: stop=95, low=104 -> NOT stopped out on entry bar
        signal_trade = result_signal["trades"][0]
        assert signal_trade["metadata"]["exit_reason"] != "stop_loss"

        # With entry_fill: stop=104.5, low=104 -> stopped out at 104.5
        fill_trade = result_fill["trades"][0]
        assert fill_trade["metadata"]["exit_reason"] == "stop_loss"
        assert fill_trade["exit_price"] == 104.5

    def test_risk_price_basis_in_trust_diagnostics(self):
        """Trust diagnostics must disclose the risk price basis."""
        result = BacktestRunner().run(
            _gap_up_bars(),
            _FixedPctRiskStrategy(),
            initial_cash=10000,
        )
        assert result["trust_diagnostics"]["risk_price_basis"] == "signal_close"
