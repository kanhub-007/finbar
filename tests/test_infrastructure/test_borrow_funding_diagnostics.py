"""Tests for explicit borrow/funding assumption diagnostics."""

import pandas as pd

from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.backtest_runner import BacktestRunner


class _OneShotShort(TradingStrategy):
    """Enter short on the first flat bar, then hold."""

    def __init__(self, position_size: float = 10.0) -> None:
        self._emitted = False
        self._size = position_size

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="borrow_diag_test",
            variant=DataMode.REAL,
            description="Borrow diagnostics test",
            required_indicators=[],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        if not self._emitted and float(position.get("size", 0) or 0) == 0:
            self._emitted = True
            return SignalResult(
                action="sell",
                direction="short",
                position_size=self._size,
            )
        return SignalResult(action="hold")

    def on_reset(self) -> None:
        self._emitted = False


class _OneShotLong(TradingStrategy):
    """Enter long on the first flat bar, then hold."""

    def __init__(self, position_size: float = 10.0) -> None:
        self._emitted = False
        self._size = position_size

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="funding_diag_test",
            variant=DataMode.REAL,
            description="Funding diagnostics test",
            required_indicators=[],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        if not self._emitted and float(position.get("size", 0) or 0) == 0:
            self._emitted = True
            return SignalResult(
                action="buy",
                direction="long",
                position_size=self._size,
            )
        return SignalResult(action="hold")

    def on_reset(self) -> None:
        self._emitted = False


def _daily_bars(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": [1000] * n,
        },
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )


class TestBorrowFundingDiagnostics:
    """Black-box tests: trust diagnostics disclose borrow/funding assumptions."""

    def test_borrow_time_basis_in_diagnostics(self):
        """Diagnostics must disclose the borrow time basis."""
        result = BacktestRunner().run(
            _daily_bars(),
            _OneShotShort(),
            initial_cash=10000,
            borrow_fee_annual_pct=0.05,
        )
        assert result["trust_diagnostics"]["borrow_time_basis"] == "calendar_day"

    def test_funding_schedule_in_diagnostics(self):
        """Diagnostics must disclose the funding schedule."""
        result = BacktestRunner().run(
            _daily_bars(),
            _OneShotLong(),
            initial_cash=10000,
            leverage=3,
            margin_mode="full",
            enable_funding=True,
            funding_rate=0.0001,
        )
        assert result["trust_diagnostics"]["funding_schedule"] == "per_bar"

    def test_funding_disabled_shows_disabled_schedule(self):
        """When funding is disabled, diagnostics show 'disabled'."""
        result = BacktestRunner().run(
            _daily_bars(),
            _OneShotLong(),
            initial_cash=10000,
        )
        assert result["trust_diagnostics"]["funding_schedule"] == "disabled"

    def test_timestamp_delta_basis_available(self):
        """borrow_time_basis can be set to timestamp_delta."""
        result = BacktestRunner().run(
            _daily_bars(),
            _OneShotShort(),
            initial_cash=10000,
            borrow_fee_annual_pct=0.05,
            borrow_time_basis="timestamp_delta",
        )
        assert result["trust_diagnostics"]["borrow_time_basis"] == "timestamp_delta"

    def test_timestamp_delta_increases_intraday_borrow_cost(self):
        """Intraday bars with timestamp_delta accrue proportional borrow.

        With hourly bars, a position held across 2 hourly bars should accrue
        more borrow than the calendar-day model (which would compute 0 days
        for same-day positions).
        """
        hourly = pd.DataFrame(
            {
                "open": [100.0, 100.0, 100.0],
                "high": [101.0, 101.0, 101.0],
                "low": [99.0, 99.0, 99.0],
                "close": [100.0, 100.0, 100.0],
                "volume": [1000, 1000, 1000],
            },
            index=pd.date_range("2024-01-01 09:00", periods=3, freq="h"),
        )

        calendar_result = BacktestRunner().run(
            hourly,
            _OneShotShort(position_size=10),
            initial_cash=10000,
            borrow_fee_annual_pct=1.0,
            borrow_time_basis="calendar_day",
        )
        ts_result = BacktestRunner().run(
            hourly,
            _OneShotShort(position_size=10),
            initial_cash=10000,
            borrow_fee_annual_pct=1.0,
            borrow_time_basis="timestamp_delta",
        )

        # Calendar-day: same-day hold = 0 days = zero borrow
        assert calendar_result["total_borrow_cost"] == 0.0
        # Timestamp-delta: 2 hourly bars held = nonzero borrow
        assert ts_result["total_borrow_cost"] > 0.0
