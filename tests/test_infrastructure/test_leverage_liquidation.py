"""Tests for maintenance-aware leveraged liquidation."""

import pandas as pd
import pytest

from finbar.core.domain.entities.leverage_config import LeverageConfig
from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.backtest_runner import BacktestRunner


class _OneShotLong(TradingStrategy):
    """Enter long on the first flat bar, then hold."""

    def __init__(self, position_size: float = 300.0) -> None:
        self._emitted = False
        self._size = position_size

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="liq_test_long",
            variant=DataMode.REAL,
            description="One long entry.",
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


class _OneShotShort(TradingStrategy):
    """Enter short on the first flat bar, then hold."""

    def __init__(self, position_size: float = 300.0) -> None:
        self._emitted = False
        self._size = position_size

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="liq_test_short",
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
                position_size=self._size,
            )
        return SignalResult(action="hold")

    def on_reset(self) -> None:
        self._emitted = False


def _adverse_long_bars(entry: float, liq_target: float) -> pd.DataFrame:
    """Bars that drop from entry to below the liquidation boundary."""
    prices = [entry, entry, entry * 0.9, liq_target, liq_target * 0.5]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        },
        index=pd.date_range("2024-01-01", periods=len(prices), freq="D"),
    )


def _adverse_short_bars(entry: float, liq_target: float) -> pd.DataFrame:
    """Bars that rise from entry to above the liquidation boundary."""
    prices = [entry, entry, entry * 1.1, liq_target, liq_target * 1.5]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        },
        index=pd.date_range("2024-01-01", periods=len(prices), freq="D"),
    )


class TestLeverageConfigLiquidation:
    """Pure unit tests for the liquidation price formula."""

    def test_long_liquidation_with_maintenance_is_above_zero_maintenance(self):
        """Adding maintenance margin moves the long liq price UP (less adverse
        move needed to liquidate)."""
        zero_maint = LeverageConfig(multiplier=3.0)
        with_maint = LeverageConfig(multiplier=3.0, maintenance_margin_pct=0.01)

        liq_zero = zero_maint.liquidation_price(100.0, "long")
        liq_with = with_maint.liquidation_price(100.0, "long")

        # zero-maintenance: 100 * (1 - 1/3) = 66.67
        assert liq_zero == 100.0 * (1.0 - 1.0 / 3.0)
        # with 1% maintenance: 100 * (1 - 1/3 + 0.01) = 67.67
        assert liq_with > liq_zero
        assert liq_with == 100.0 * (1.0 - 1.0 / 3.0 + 0.01)

    def test_short_liquidation_with_maintenance_is_below_zero_maintenance(self):
        """Adding maintenance margin moves the short liq price DOWN."""
        zero_maint = LeverageConfig(multiplier=3.0)
        with_maint = LeverageConfig(multiplier=3.0, maintenance_margin_pct=0.01)

        liq_zero = zero_maint.liquidation_price(100.0, "short")
        liq_with = with_maint.liquidation_price(100.0, "short")

        assert liq_with < liq_zero
        assert liq_with == 100.0 * (1.0 + 1.0 / 3.0 - 0.01)

    def test_zero_maintenance_preserves_current_behavior(self):
        """maintenance_margin_pct=0.0 must match the existing formula."""
        config = LeverageConfig(multiplier=3.0, maintenance_margin_pct=0.0)

        assert config.liquidation_price(100.0, "long") == pytest.approx(
            100.0 * (2.0 / 3.0)
        )
        assert config.liquidation_price(100.0, "short") == pytest.approx(
            100.0 * (4.0 / 3.0)
        )

    def test_spot_has_no_liquidation(self):
        """Leverage <= 1 returns entry price (no liquidation)."""
        config = LeverageConfig(multiplier=1.0, maintenance_margin_pct=0.005)
        assert config.liquidation_price(100.0, "long") == 100.0


class TestBacktestMaintenanceAwareLiquidation:
    """Integration tests: liquidation fires at maintenance-aware boundary."""

    def test_long_liquidates_earlier_with_maintenance_margin(self):
        """With maintenance margin, the long position liquidates at a higher
        price than without — the liquidation fires on an earlier bar."""
        bars = _adverse_long_bars(entry=100.0, liq_target=30.0)

        zero_maint = BacktestRunner().run(
            bars,
            _OneShotLong(position_size=300),
            initial_cash=10000,
            leverage=3,
            maintenance_margin_pct=0.0,
        )
        with_maint = BacktestRunner().run(
            bars,
            _OneShotLong(position_size=300),
            initial_cash=10000,
            leverage=3,
            maintenance_margin_pct=0.05,
        )

        zero_trade = zero_maint["trades"][0]
        maint_trade = with_maint["trades"][0]

        assert zero_trade["metadata"]["exit_reason"] == "liquidation"
        assert maint_trade["metadata"]["exit_reason"] == "liquidation"
        # Maintenance-aware liq price is higher → exits earlier → at a higher price
        assert maint_trade["exit_price"] > zero_trade["exit_price"]

    def test_maintenance_margin_in_trust_diagnostics(self):
        """Trust diagnostics must disclose maintenance_margin_pct."""
        bars = _adverse_long_bars(entry=100.0, liq_target=30.0)
        result = BacktestRunner().run(
            bars,
            _OneShotLong(position_size=300),
            initial_cash=10000,
            leverage=3,
            maintenance_margin_pct=0.005,
        )

        assert result["trust_diagnostics"]["maintenance_margin_pct"] == 0.005

    def test_reconciliation_zero_after_liquidation(self):
        """Reconciliation must still be zero after a liquidation."""
        bars = _adverse_long_bars(entry=100.0, liq_target=30.0)
        result = BacktestRunner().run(
            bars,
            _OneShotLong(position_size=300),
            initial_cash=10000,
            leverage=3,
            maintenance_margin_pct=0.01,
        )

        assert result["reconciliation_error"] == 0.0
