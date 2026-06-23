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


# =========================================================================
# Scenarios 4-7: rolling_scalar_series window vs calculator lookback
#   Root cause: handlers in microstructure.py call rolling_scalar_series
#   with the default window=20, but the scalar calculators need a larger
#   lookback (60 for spreads, 21 for liu/resiliency). The wrapper passes a
#   20-bar slice; the calculator sees len(slice) < lookback and returns
#   None -> the wrapper writes NaN for every bar.
# =========================================================================


class TestRollingScalarWindowMatchesLookback:
    """Scenarios 4, 5, 6, 7 — rolling-scalar metrics must be non-null at tail."""

    @pytest.mark.parametrize(
        ("metric", "min_bars"),
        [
            # Calculator default lookback=60; wrapper window must be >= 60.
            ("effective_tick_spread", 65),
            ("lot_zero_return_spread", 65),
            # Calculator default lookback=21.
            ("liu_illiq", 25),
            # Calculator needs lookback(20) + lag(1) = 21.
            ("resiliency_autocorr", 25),
        ],
    )
    def test_rolling_scalar_metric_non_null_at_tail(
        self, calc, metric, min_bars
    ):
        """The metric column must contain non-NaN values at the tail.

        With a too-small wrapper window the calculator returns None on
        every 20-bar slice, so the whole column is NaN. We build exactly
        ``min_bars`` rows so there is enough data to clear warmup once
        the window is fixed.
        """
        rng = np.random.default_rng(seed=7)
        n = max(min_bars, 30)
        close = 100.0 + rng.uniform(-5.0, 5.0, n).cumsum()
        df = pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
            }
        )
        df.index = pd.date_range("2026-01-01", periods=n, freq="D")

        result = calc.calculate(df, [metric])
        assert metric in result.columns, f"{metric} column missing"

        tail = result[metric].tail(5)
        assert tail.notna().any(), (
            f"{metric} all-NaN at tail (wrapper window < calculator lookback)"
        )

    def test_resiliency_autocorr_in_valid_range(self, calc):
        """Scenario 7: autocorrelation must be a float in [-1, 1]."""
        rng = np.random.default_rng(seed=11)
        n = 40
        close = 100.0 + rng.uniform(-2.0, 2.0, n).cumsum()
        df = pd.DataFrame(
            {
                "open": close,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1_000_000.0,
            }
        )
        df.index = pd.date_range("2026-01-01", periods=n, freq="D")

        result = calc.calculate(df, ["resiliency_autocorr"])
        non_null = result["resiliency_autocorr"].dropna()
        assert len(non_null) > 0
        assert ((non_null >= -1.0) & (non_null <= 1.0)).all()

    def test_liu_illiq_zero_for_never_zero_volume(self, calc):
        """Scenario 6: crypto-style constant volume -> 0.0 zero-volume days."""
        n = 30
        close = pd.Series(np.linspace(100.0, 120.0, n))
        df = pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000.0,
            }
        )
        df.index = pd.date_range("2026-01-01", periods=n, freq="D")

        result = calc.calculate(df, ["liu_illiq"])
        non_null = result["liu_illiq"].dropna()
        assert len(non_null) > 0
        assert (non_null == 0.0).all()


# =========================================================================
# Scenario 8: proxy_atr / proxy_ib_high / proxy_ib_low / proxy_expected_move
#   Root cause (verified): the proxy handlers in inside_bar.py are NEVER
#   dispatched — pandas_ta_indicator_calculator.py short-circuits every
#   name.startswith("proxy_") to enrich_dataframe_with_proxies(). Those 4
#   proxies are missing because (a) proxy_atr was only computed by the dead
#   handler, and (b) proxy_ib_high/low/expected_move were gated behind
#   `if "atr" in result.columns`, but the pandas_ta atr column is never
#   added unless separately requested. Fix (Option B): compute them
#   unconditionally inside enrich_dataframe_with_proxies.
# =========================================================================


class TestProxyEnrichmentAlwaysComputesAtrDependents:
    """Scenario 8 — proxy_atr and its dependents without requesting atr."""

    def test_all_four_proxy_columns_present_without_atr(self, calc):
        """Request proxies WITHOUT atr; all 4 columns must appear."""
        rng = np.random.default_rng(seed=3)
        n = 40
        close = 100.0 + rng.uniform(-3.0, 3.0, n).cumsum()
        df = pd.DataFrame(
            {
                "open": close,
                "high": close + 1.5,
                "low": close - 1.5,
                "close": close,
                "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
            }
        )
        df.index = pd.date_range("2026-01-01", periods=n, freq="D")

        result = calc.calculate(
            df,
            ["proxy_atr", "proxy_ib_high", "proxy_ib_low", "proxy_expected_move"],
        )
        for col in (
            "proxy_atr",
            "proxy_ib_high",
            "proxy_ib_low",
            "proxy_expected_move",
        ):
            assert col in result.columns, f"{col} missing"

    def test_proxy_columns_non_null_after_warmup(self, calc):
        """After the 14-bar ATR warmup, all 4 proxies must be non-null."""
        rng = np.random.default_rng(seed=4)
        n = 40
        close = 100.0 + rng.uniform(-3.0, 3.0, n).cumsum()
        df = pd.DataFrame(
            {
                "open": close,
                "high": close + 1.5,
                "low": close - 1.5,
                "close": close,
                "volume": 1_000_000.0,
            }
        )
        df.index = pd.date_range("2026-01-01", periods=n, freq="D")

        result = calc.calculate(
            df, ["proxy_atr", "proxy_ib_high", "proxy_ib_low", "proxy_expected_move"]
        )
        for col in (
            "proxy_atr",
            "proxy_ib_high",
            "proxy_ib_low",
            "proxy_expected_move",
        ):
            tail = result[col].tail(5)
            assert not tail.isna().any(), f"{col} has NaN at tail: {tail.tolist()}"

    def test_proxy_atr_positive_and_scales_with_range(self, calc):
        """proxy_atr must be positive and grow when bar range grows."""
        n = 40
        idx = pd.date_range("2026-01-01", periods=n, freq="D")
        close = pd.Series(np.linspace(100.0, 110.0, n), index=idx)

        small = pd.DataFrame(
            {
                "open": close,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1_000_000.0,
            },
            index=idx,
        )
        large = pd.DataFrame(
            {
                "open": close,
                "high": close + 5.0,
                "low": close - 5.0,
                "close": close,
                "volume": 1_000_000.0,
            },
            index=idx,
        )

        small_atr = calc.calculate(small, ["proxy_atr"])["proxy_atr"].iloc[-1]
        large_atr = calc.calculate(large, ["proxy_atr"])["proxy_atr"].iloc[-1]
        assert small_atr > 0.0
        assert large_atr > small_atr

    def test_proxy_ib_high_above_proxy_ib_low(self, calc):
        """proxy_ib_high must be > proxy_ib_low at every bar (open +/- 0.1*ATR)."""
        rng = np.random.default_rng(seed=5)
        n = 40
        close = 100.0 + rng.uniform(-2.0, 2.0, n).cumsum()
        df = pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000.0,
            }
        )
        df.index = pd.date_range("2026-01-01", periods=n, freq="D")

        result = calc.calculate(df, ["proxy_ib_high", "proxy_ib_low", "proxy_atr"])
        tail = result.tail(20)
        assert (tail["proxy_ib_high"] > tail["proxy_ib_low"]).all()

    def test_proxy_family_independent_of_atr_request_order(self, calc):
        """Requesting atr before vs after a proxy must not change proxy output.

        Guards against the dispatch-ordering trap: proxies must use their own
        proxy_atr, never the pandas_ta atr column (which may or may not be
        present when enrichment runs, depending on request order).
        """
        rng = np.random.default_rng(seed=9)
        n = 40
        close = 100.0 + rng.uniform(-2.0, 2.0, n).cumsum()
        base = pd.DataFrame(
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000.0,
            }
        )
        base.index = pd.date_range("2026-01-01", periods=n, freq="D")

        proxy_first = calc.calculate(base.copy(), ["proxy_ib_high", "atr"])[
            "proxy_ib_high"
        ]
        atr_first = calc.calculate(base.copy(), ["atr", "proxy_ib_high"])[
            "proxy_ib_high"
        ]
        pd.testing.assert_series_equal(proxy_first, atr_first)


# =========================================================================
# Scenario 9: poc_rejection / edge_volume_building on intraday
#
# ⚠️ SPEC DISCREPANCY (flagged to user, not silently "fixed"):
# The corrected spec (research/03) hypothesised compute_amt_signals raises an
# exception on intraday. Diagnosis with random, multi-day, and real-handler-
# enriched intraday fixtures shows compute_amt_signals does NOT raise — it
# returns clean boolean Series whenever its dependencies are present. The
# reproducible failure is a dependency-resolution gap: poc_rejection
# (requires={vp_poc,atr}) and edge_volume_building (requires={vp_vah,vp_val,
# rvol}) get NaN when their deps are not co-requested. That belongs to the
# Slice 2 "check_metric warns on unsatisfied non-OHLCV requires" scenario
# (same class as vol_buffer_high, research/03 §2), NOT an in-code exception.
#
# The tests below pin the ACTUAL contract from the spec's "Then" clause:
# when deps are present, poc_rejection / edge_volume_building must be bool
# Series with no NaN, and compute_amt_signals must not raise.
# =========================================================================


class TestAmtSignalsIntradayContract:
    """Scenario 9 — characterization of the actual (non-exception) behavior."""

    def test_compute_amt_signals_does_not_raise_on_intraday(self):
        """compute_amt_signals must return bool columns, no NaN, on intraday."""
        from finbar_strategy_runtime.domain.services.amt_signals import (
            compute_amt_signals,
        )

        rng = np.random.default_rng(seed=21)
        n = 120  # 5 days of 1h bars
        idx = pd.date_range("2026-01-05", periods=n, freq="1h")
        close = 100.0 + rng.uniform(-0.5, 0.5, n).cumsum()
        enriched = pd.DataFrame(
            {
                "open": close,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "volume": rng.integers(100, 1000, n).astype(float),
                "vp_poc": close,
                "vp_vah": close + 1.0,
                "vp_val": close - 1.0,
                "at_poc": rng.random(n) < 0.3,
                "near_vah": rng.random(n) < 0.3,
                "near_val": rng.random(n) < 0.3,
                "inside_value": True,
                "above_value": False,
                "below_value": False,
                "rvol": 1.0,
                "atr": 1.5,
            },
            index=idx,
        )

        result = compute_amt_signals(enriched)

        assert result["poc_rejection"].dtype == bool
        assert result["edge_volume_building"].dtype == bool
        assert result["poc_rejection"].notna().all()
        assert result["edge_volume_building"].notna().all()

    def test_amt_signals_via_dispatch_with_deps_present(self, calc):
        """Via dispatch, with deps co-requested, AMT signals are bool + non-null."""
        rng = np.random.default_rng(seed=22)
        n = 120
        idx = pd.date_range("2026-01-05", periods=n, freq="1h")
        close = 100.0 + rng.uniform(-0.5, 0.5, n).cumsum()
        df = pd.DataFrame(
            {
                "open": close,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "volume": rng.integers(100, 1000, n).astype(float),
            },
            index=idx,
        )
        result = calc.calculate(
            df,
            [
                "atr",
                "rvol",
                "vp_poc",
                "vp_vah",
                "vp_val",
                "inside_value",
                "above_value",
                "below_value",
                "at_poc",
                "near_vah",
                "near_val",
                "poc_rejection",
                "edge_volume_building",
            ],
        )
        assert result["poc_rejection"].dtype == bool
        assert result["poc_rejection"].notna().all()
        assert result["edge_volume_building"].dtype == bool
        assert result["edge_volume_building"].notna().all()
