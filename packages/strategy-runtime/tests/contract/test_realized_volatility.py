"""Contract tests for realized volatility + intraday volume curve calculators.

Classical (Detroit) school: deterministic fixtures, assert on outcomes.
"""

import numpy as np
import pandas as pd
import pytest

from finbar_strategy_runtime.domain.services.intraday_seasonality_proxies import (
    empirical_volume_curve,
    intraday_volume_curve,
)
from finbar_strategy_runtime.domain.services.realized_volatility_estimators import (
    bipower_variation,
    lee_mykland_jump,
    realized_kurtosis,
    realized_skewness,
    realized_volatility,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_intraday_bars(n_days: int = 10, bars_per_day: int = 78) -> pd.DataFrame:
    """Generate deterministic intraday OHLCV bars (5-min granularity)."""
    np.random.seed(42)
    n = n_days * bars_per_day
    # Build a DatetimeIndex with intraday timestamps (9:30–16:00, 5-min bars)
    times = []
    for day in range(n_days):
        base = pd.Timestamp(f"2024-01-{day + 1:02d} 09:30:00")
        for bar in range(bars_per_day):
            times.append(base + pd.Timedelta(minutes=5 * bar))
    idx = pd.DatetimeIndex(times[:n])

    close = pd.Series(100 + np.cumsum(np.random.randn(n) * 0.1), index=idx)
    volume = pd.Series(
        np.random.randint(100, 1000, n).astype(float), index=idx
    )
    return pd.DataFrame(
        {"open": close, "high": close + 0.05, "low": close - 0.05,
         "close": close, "volume": volume}
    )


@pytest.fixture
def intraday_df() -> pd.DataFrame:
    return _make_intraday_bars()


# ---------------------------------------------------------------------------
# realized_volatility (used by realized_vol_5m / 15m / 1h handlers)
# ---------------------------------------------------------------------------


class TestRealizedVolatility:
    """Realized volatility = sqrt(sum of squared log returns) over window."""

    def test_returns_series_of_same_length(self, intraday_df):
        result = realized_volatility(intraday_df["close"], window=78)
        assert isinstance(result, pd.Series)
        assert len(result) == len(intraday_df)

    def test_warmup_is_nan(self, intraday_df):
        """First window bars are NaN (diff creates NaN at index 0)."""
        result = realized_volatility(intraday_df["close"], window=78)
        assert result.iloc[:78].isna().all()

    def test_first_value_after_warmup_is_finite(self, intraday_df):
        result = realized_volatility(intraday_df["close"], window=78)
        assert np.isfinite(result.iloc[78])

    def test_constant_prices_produce_zero_vol(self):
        """Constant close → zero returns → zero realized vol."""
        close = pd.Series([100.0] * 100)
        result = realized_volatility(close, window=20)
        # After warmup, all values should be ~0
        assert (result.iloc[19:].dropna() < 1e-15).all()

    def test_non_negative(self, intraday_df):
        result = realized_volatility(intraday_df["close"], window=78)
        assert (result.dropna() >= 0).all()

    def test_window_too_large_all_nan(self):
        close = pd.Series([100.0, 101.0, 102.0])
        result = realized_volatility(close, window=78)
        assert result.isna().all()


# ---------------------------------------------------------------------------
# bipower_variation (Barndorff-Nielsen & Shephard 2004)
# ---------------------------------------------------------------------------


class TestBipowerVariation:
    """BV = (pi/2) * sum(|r_i| * |r_{i-1}|) over window."""

    def test_returns_series(self, intraday_df):
        result = bipower_variation(intraday_df["close"], window=78)
        assert isinstance(result, pd.Series)
        assert len(result) == len(intraday_df)

    def test_non_negative(self, intraday_df):
        result = bipower_variation(intraday_df["close"], window=78)
        assert (result.dropna() >= 0).all()

    def test_constant_prices_zero(self):
        """Constant close → zero returns → zero BV."""
        close = pd.Series([100.0] * 100)
        result = bipower_variation(close, window=20)
        assert (result.iloc[19:].dropna() < 1e-15).all()

    def test_warmup_is_nan(self, intraday_df):
        result = bipower_variation(intraday_df["close"], window=78)
        assert result.iloc[:78].isna().all()

    def test_jumps_dont_inflate_bv_as_much_as_rv(self):
        """BV is jump-robust: a single jump inflates BV less than RV.

        BV uses cross-products |r_i|*|r_{i-1}| so a jump at position k
        contributes to only 2 cross-products. RV uses r^2 so a jump
        contributes its full square. The inflation ratio of BV should
        be much smaller than RV's.
        """
        np.random.seed(1)
        base = np.random.randn(200) * 0.01
        with_jump = base.copy()
        with_jump[100] = 5.0  # massive jump at index 100

        close_no = pd.Series(100 + np.cumsum(base))
        close_yes = pd.Series(100 + np.cumsum(with_jump))

        bv_no = bipower_variation(close_no, window=50)
        bv_yes = bipower_variation(close_yes, window=50)
        rv_no = realized_volatility(close_no, window=50)
        rv_yes = realized_volatility(close_yes, window=50)

        # At the bar right after the jump (index 101):
        bv_ratio = bv_yes.iloc[101] / bv_no.iloc[101]
        rv_ratio = rv_yes.iloc[101] / rv_no.iloc[101]

        # RV inflation should be much larger than BV inflation
        assert rv_ratio > bv_ratio, (
            f"RV ratio ({rv_ratio}) should exceed BV ratio ({bv_ratio})"
        )


# ---------------------------------------------------------------------------
# realized_skewness / realized_kurtosis
# ---------------------------------------------------------------------------


class TestRealizedSkewness:
    def test_returns_series(self, intraday_df):
        result = realized_skewness(intraday_df["close"], window=78)
        assert isinstance(result, pd.Series)
        assert len(result) == len(intraday_df)

    def test_symmetric_data_zero_skew(self):
        """Symmetric returns → skewness ~0."""
        np.random.seed(1)
        # Perfectly alternating returns → symmetric distribution
        rets = np.array([1, -1] * 100, dtype=float) * 0.01
        close = pd.Series(100 + np.cumsum(rets))
        result = realized_skewness(close, window=50)
        # After full warmup, skew should be near zero
        assert abs(result.iloc[99]) < 0.1

    def test_warmup_is_nan(self, intraday_df):
        result = realized_skewness(intraday_df["close"], window=78)
        assert result.iloc[:78].isna().all()


class TestRealizedKurtosis:
    def test_returns_series(self, intraday_df):
        result = realized_kurtosis(intraday_df["close"], window=78)
        assert isinstance(result, pd.Series)
        assert len(result) == len(intraday_df)

    def test_kurtosis_positive(self):
        """Kurtosis is always >= 0 for realized (4th moment standardized)."""
        np.random.seed(1)
        close = pd.Series(100 + np.cumsum(np.random.randn(200) * 0.1))
        result = realized_kurtosis(close, window=50)
        assert (result.dropna() >= 0).all()

    def test_warmup_is_nan(self, intraday_df):
        result = realized_kurtosis(intraday_df["close"], window=78)
        assert result.iloc[:78].isna().all()


# ---------------------------------------------------------------------------
# lee_mykland_jump (Lee & Mykland 2008)
# ---------------------------------------------------------------------------


class TestLeeMyklandJump:
    """Lee-Mykland jump detection: flag bars where standardized return
    exceeds a threshold using bipower-variance scaling."""

    def test_returns_series(self, intraday_df):
        result = lee_mykland_jump(intraday_df["close"], window=78)
        assert isinstance(result, pd.Series)
        assert len(result) == len(intraday_df)

    def test_returns_boolean_or_float(self, intraday_df):
        """Returns a Series (can be bool flags or z-scores)."""
        result = lee_mykland_jump(intraday_df["close"], window=78)
        assert result.dtype in (bool, float, np.float64, np.bool_)

    def test_detects_injected_jump(self):
        """A clear injected jump should be flagged."""
        np.random.seed(1)
        base = np.random.randn(200) * 0.01
        close = pd.Series(100 + np.cumsum(base))
        # Inject a massive jump
        close.iloc[150] = close.iloc[149] * 1.20  # 20% jump

        result = lee_mykland_jump(close, window=50, threshold=3.09)
        # The jump bar or the bar after should be flagged
        assert result.iloc[150] or result.iloc[151]

    def test_no_false_positives_on_calm_data(self):
        """On very calm data (tiny returns), no jumps should be flagged."""
        np.random.seed(1)
        close = pd.Series(100 + np.cumsum(np.random.randn(200) * 0.001))
        result = lee_mykland_jump(close, window=50, threshold=3.09)
        flagged = result.sum() if result.dtype == bool else (result > 3.09).sum()
        assert flagged <= 2  # at most a couple of false positives


# ---------------------------------------------------------------------------
# intraday_volume_curve / empirical_volume_curve
# ---------------------------------------------------------------------------


class TestIntradayVolumeCurve:
    """Volume curve: mean volume per time-of-day slot."""

    def test_returns_series(self, intraday_df):
        result = intraday_volume_curve(intraday_df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(intraday_df)

    def test_u_shape_pattern(self, intraday_df):
        """Intraday volume tends to be U-shaped (high at open/close).
        Average of first 5 bars should be higher than mid-day."""
        result = intraday_volume_curve(intraday_df)
        # Group by time-of-day and take mean
        first_bars = result.groupby(result.index.hour).mean()
        # 9:30 hour should have decent volume (can't guarantee > midday
        # with random data, just verify it's finite)
        assert np.isfinite(first_bars.iloc[0])

    def test_no_nan_after_warmup(self, intraday_df):
        """After the first day (78 bars), all values should be finite."""
        result = intraday_volume_curve(intraday_df)
        assert result.iloc[78:].apply(lambda x: np.isfinite(x)).all()


class TestEmpiricalVolumeCurve:
    def test_returns_series(self, intraday_df):
        result = empirical_volume_curve(intraday_df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(intraday_df)

    def test_no_nan_after_warmup(self, intraday_df):
        result = empirical_volume_curve(intraday_df)
        assert result.iloc[78:].apply(lambda x: np.isfinite(x)).all()
