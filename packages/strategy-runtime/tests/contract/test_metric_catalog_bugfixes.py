"""Regression tests for the metric-catalog bug-fix spec (2026-06-16).

Classical (Detroit) school tests: real ``PandasTaIndicatorCalculator``
dispatch, deterministic fixtures, assert on OUTCOMES (non-null values at
tail, value ranges, value types). No mocks.

These tests guard against silent regressions of the bugs documented in
``specs/2026-06-16_fix-metric-catalog-bugs``. The bugs surface as silent
``NaN`` columns because ``PandasTaIndicatorCalculator`` catches handler
exceptions and writes ``np.nan``. Existing weak contract tests only
assert ``metric in result.columns`` and therefore pass even when a
handler crashed — these stronger tests assert the column actually
contains meaningful data.
"""

import numpy as np
import pandas as pd
import pytest

from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def calc() -> PandasTaIndicatorCalculator:
    """Fresh calculator instance."""
    return PandasTaIndicatorCalculator()


@pytest.fixture
def daily_ohlcv_60() -> pd.DataFrame:
    """60-bar daily OHLCV with trend + volume.

    Enough bars to clear every warmup in Slice 1 (zone score volume SMA 20,
    spread lookback 60 via the rolling wrapper, etc.).
    """
    rng = np.random.default_rng(seed=42)
    n = 60
    uptrend = np.linspace(100.0, 200.0, 30)
    downtrend = np.linspace(200.0, 150.0, 30)
    close = np.concatenate([uptrend, downtrend])
    jitter = rng.uniform(-1.5, 1.5, n)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0 + np.abs(jitter),
            "low": close - 1.0 - np.abs(jitter),
            "close": close,
            "volume": rng.integers(1_000_000, 10_000_000, n).astype(float),
        }
    )
    df.index = pd.date_range("2026-01-01", periods=n, freq="D")
    return df


# =========================================================================
# Scenarios 1-3: supply/demand zone handler argument mismatch
#   Root cause: handlers in price_action.py call demand_zone_score,
#   supply_zone_score, zone_failure_bullish/bearish with only 3 args
#   (high, low, close) but the functions require a 4th 'volume' arg,
#   raising TypeError -> dispatch silently writes NaN.
# =========================================================================


class TestSupplyDemandZoneHandlersNonNullable:
    """Scenarios 1, 2, 3 — zone metrics must yield non-null, typed values."""

    @pytest.mark.parametrize(
        "metric",
        ["demand_zone_score", "supply_zone_score"],
    )
    def test_zone_score_is_non_null_int_0_to_6(self, calc, daily_ohlcv_60, metric):
        """Scenario 1 & 2: score column must hold integers in 0..6 at tail."""
        result = calc.calculate(daily_ohlcv_60, [metric])
        assert metric in result.columns, f"{metric} column missing"

        tail = result[metric].tail(5)
        assert tail.notna().any(), f"{metric} is all-NaN at tail (handler crashed)"
        # Values are ints clamped to [0, 6].
        non_null = tail.dropna()
        assert ((non_null >= 0) & (non_null <= 6)).all(), (
            f"{metric} values out of [0,6]: {non_null.tolist()}"
        )

    @pytest.mark.parametrize(
        "metric",
        ["zone_failure_bullish", "zone_failure_bearish"],
    )
    def test_zone_failure_is_boolean_series(self, calc, daily_ohlcv_60, metric):
        """Scenario 3: failure flags must be boolean Series (never NaN)."""
        result = calc.calculate(daily_ohlcv_60, [metric])
        assert metric in result.columns, f"{metric} column missing"

        col = result[metric]
        # All-NaN means the handler crashed inside dispatch.
        assert not col.isna().all(), f"{metric} is all-NaN (handler crashed)"
        assert col.dtype == bool, f"{metric} dtype {col.dtype}, expected bool"
