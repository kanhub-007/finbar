"""Contract tests for price-action indicator handlers — Scenario 3.1.

Verifies the PandasTaIndicatorCalculator dispatches to the new price-action
calculators (Fibonacci, Bill Williams, trend structure, SMC, VSA,
supply/demand, Hurst, market regime).
"""

import numpy as np
import pandas as pd
import pytest

from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    """60-bar OHLCV DataFrame with trend + reversal for price-action metrics."""
    n = 60
    uptrend = list(np.linspace(100, 200, 30))
    downtrend = list(np.linspace(200, 150, 30))
    close = pd.Series(uptrend + downtrend)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.random.randint(1000, 10000, n).astype(float),
        }
    )
    df.index = pd.date_range("2024-01-01", periods=n, freq="D")
    return df


@pytest.fixture
def calc() -> PandasTaIndicatorCalculator:
    return PandasTaIndicatorCalculator()


class TestFibonacciHandlers:
    @pytest.mark.parametrize(
        "metric",
        [
            "fib_382_retrace",
            "fib_500_retrace",
            "fib_618_retrace",
            "fib_1618_extension",
            "fib_confluence_score",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestBillWilliamsHandlers:
    @pytest.mark.parametrize(
        "metric",
        [
            "awesome_oscillator",
            "accelerator_oscillator",
            "alligator_jaw",
            "alligator_teeth",
            "alligator_lips",
            "alligator_status",
            "williams_fractal_high",
            "williams_fractal_low",
            "zone_signal",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestTrendStructureHandlers:
    @pytest.mark.parametrize(
        "metric",
        [
            "swing_high_n",
            "swing_low_n",
            "hh_hl_pattern",
            "lh_ll_pattern",
            "volume_trend_confirmation",
            "trend_phase",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestSMCHandlers:
    @pytest.mark.parametrize(
        "metric",
        [
            "bullish_fvg",
            "bearish_fvg",
            "bullish_order_block",
            "bearish_order_block",
            "breaker_block_bullish",
            "breaker_block_bearish",
            "liquidity_sweep_high",
            "liquidity_sweep_low",
            "bos",
            "choch",
            "premium_discount_zone",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestVSAHandlers:
    @pytest.mark.parametrize(
        "metric",
        [
            "no_demand",
            "no_supply",
            "stopping_volume",
            "climax_volume",
            "effort_to_rise",
            "effort_to_fall",
            "effort_result_divergence",
            "bag_holding",
            "shakeout",
            "vsa_test_signal",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestSupplyDemandHandlers:
    @pytest.mark.parametrize(
        "metric",
        [
            "demand_zone_low",
            "demand_zone_high",
            "demand_zone_score",
            "supply_zone_low",
            "supply_zone_high",
            "supply_zone_score",
            "zone_failure_bullish",
            "zone_failure_bearish",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestHurstHandlers:
    @pytest.mark.parametrize(
        "metric",
        ["hurst_exponent", "fractal_regime"],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestMarketRegimeHandlers:
    @pytest.mark.parametrize(
        "metric",
        ["market_regime", "day_type_classification"],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns
