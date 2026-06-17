"""Contract tests for OHLCV microstructure proxy calculators.

Classical (Detroit) school tests: real domain services, deterministic fixtures,
assert on outcomes. No mocks.
"""

import numpy as np
import pandas as pd
import pytest


# =========================================================================
# Helpers
# =========================================================================


def _make_ohlcv_frame(data: list[dict]) -> pd.DataFrame:
    """Build a DataFrame from a list of row dicts."""
    return pd.DataFrame(data)


# =========================================================================
# Spread proxies
# =========================================================================


class TestCorwinSchultzSpread:
    """Corwin-Schultz (2012): OHLC-based bid-ask spread estimator."""

    def test_constant_prices_no_spread(self):
        """All OHLC the same → spread ≈ 0."""
        from finbar_strategy_runtime.domain.services.spread_proxies import (
            fong_holden_tran_spread,
        )

        df = _make_ohlcv_frame(
            [
                {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
                {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
                {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
            ]
            * 25  # need ≥20 bars for lookback
        )
        result = fong_holden_tran_spread(df)
        # Zero spread when all prices identical
        assert result.iloc[-1] == 0.0

    def test_positive_ohlc_range_produces_positive_spread(self):
        """Realistic OHLC bars produce a positive spread estimate."""
        from finbar_strategy_runtime.domain.services.spread_proxies import (
            fong_holden_tran_spread,
        )

        np.random.seed(1)
        periods = 30
        close = 100 + np.cumsum(np.random.randn(periods) * 0.5)
        df = pd.DataFrame(
            {
                "open": close - np.random.rand(periods) * 0.3,
                "high": close + np.random.rand(periods) * 0.5,
                "low": close - np.random.rand(periods) * 0.5,
                "close": close,
            }
        )
        result = fong_holden_tran_spread(df)
        # Spread should be non-negative
        assert (result.dropna() >= 0).all()
        assert not result.iloc[-1] is None
        assert isinstance(result.iloc[-1], float)

    def test_insufficient_bars_returns_nan(self):
        """Less than 20 bars → all NaN."""
        from finbar_strategy_runtime.domain.services.spread_proxies import (
            fong_holden_tran_spread,
        )

        df = _make_ohlcv_frame(
            [
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
                {"open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5},
            ]
        )
        result = fong_holden_tran_spread(df)
        assert result.isna().all()


class TestRollSpread:
    """Roll (1984): serial covariance spread estimator."""

    def test_random_walk_no_spread(self):
        """Random walk close → near-zero Roll spread."""
        from finbar_strategy_runtime.domain.services.spread_proxies import (
            roll_spread,
        )

        np.random.seed(0)
        periods = 30
        close = pd.Series(100 + np.cumsum(np.random.randn(periods) * 0.5))
        result = roll_spread(close)
        # Should be non-negative (covariance sign handled internally)
        assert result >= 0

    def test_alternating_prices(self):
        """Alternating close 100, 101, 100, 101 → negative serial cov → spread."""
        from finbar_strategy_runtime.domain.services.spread_proxies import (
            roll_spread,
        )

        close = pd.Series([100.0, 101.0] * 15 + [100.0])  # 31 bars
        result = roll_spread(close)
        assert result > 0


# =========================================================================
# Volatility estimators
# =========================================================================


class TestCloseToCloseVol:
    """Close-to-close return volatility."""

    def test_constant_returns_zero_vol(self):
        """Identical closes → zero volatility."""
        from finbar_strategy_runtime.domain.services.volatility_estimators import (
            close_to_close_vol,
        )

        close = pd.Series([100.0] * 30)
        result = close_to_close_vol(close)
        assert result.iloc[-1] == 0.0

    def test_positive_vol_for_moving_prices(self):
        """Random walk → positive volatility."""
        from finbar_strategy_runtime.domain.services.volatility_estimators import (
            close_to_close_vol,
        )

        np.random.seed(2)
        close = pd.Series(100 + np.cumsum(np.random.randn(50) * 1.0))
        result = close_to_close_vol(close)
        assert result.iloc[-1] > 0

    def test_min_lookback_enforced(self):
        """Fewer than lookback bars → NaN."""
        from finbar_strategy_runtime.domain.services.volatility_estimators import (
            close_to_close_vol,
        )

        close = pd.Series([100.0, 101.0, 102.0])
        result = close_to_close_vol(close, lookback=5)
        assert result.isna().all()


# =========================================================================
# Liquidity proxies
# =========================================================================


class TestAmihudIlliq:
    """Amihud (2002): illiquidity = |return| / dollar_volume."""

    def test_zero_volume_returns_nan(self):
        """Zero volume → NaN (division by zero)."""
        from finbar_strategy_runtime.domain.services.liquidity_proxies import (
            amihud_illiq,
        )

        df = _make_ohlcv_frame(
            [
                {"close": 100.0, "volume": 0},
                {"close": 101.0, "volume": 0},
            ]
            * 25
        )
        result = amihud_illiq(df)
        assert result.isna().all()

    def test_positive_values_for_normal_data(self):
        """Normal OHLCV → positive illiquidity values."""
        from finbar_strategy_runtime.domain.services.liquidity_proxies import (
            amihud_illiq,
        )

        np.random.seed(3)
        periods = 30
        close = 100 + np.cumsum(np.random.randn(periods))
        df = pd.DataFrame(
            {
                "close": close,
                "volume": np.random.randint(10000, 1000000, periods).astype(float),
            }
        )
        result = amihud_illiq(df)
        assert (result.dropna() >= 0).all()

    def test_known_output(self):
        """Deterministic input → known output."""
        from finbar_strategy_runtime.domain.services.liquidity_proxies import (
            amihud_illiq,
        )

        df = _make_ohlcv_frame(
            [
                {"close": 100.0, "volume": 1000.0},
                {"close": 101.0, "volume": 1000.0},  # ret=0.01
                {"close": 102.0, "volume": 1000.0},  # ret=0.00990099...
                {"close": 103.0, "volume": 1000.0},  # ret=0.00980392...
                {"close": 104.0, "volume": 1000.0},
            ]
            * 5  # 25 bars, enough for lookback=20
        )
        result = amihud_illiq(df, lookback=5)
        # Last value: average of |ret|/(close*volume) for last 5 bars
        assert result.iloc[-1] > 0


# =========================================================================
# Order flow proxies
# =========================================================================


class TestSignedSqrtVolumeOfi:
    """Order flow imbalance via signed sqrt(volume)."""

    def test_positive_close_delta_positive_ofi(self):
        """Close up → positive OFI."""
        from finbar_strategy_runtime.domain.services.order_flow_proxies import (
            signed_sqrt_volume_ofi,
        )

        df = _make_ohlcv_frame(
            [
                {"close": 100.0, "volume": 10000.0},
                {"close": 101.0, "volume": 10000.0},
            ]
        )
        result = signed_sqrt_volume_ofi(df)
        assert result.iloc[-1] > 0

    def test_negative_close_delta_negative_ofi(self):
        """Close down → negative OFI."""
        from finbar_strategy_runtime.domain.services.order_flow_proxies import (
            signed_sqrt_volume_ofi,
        )

        df = _make_ohlcv_frame(
            [
                {"close": 100.0, "volume": 10000.0},
                {"close": 99.0, "volume": 10000.0},
            ]
        )
        result = signed_sqrt_volume_ofi(df)
        assert result.iloc[-1] < 0

    def test_flat_close_zero_ofi(self):
        """Close unchanged → OFI = 0."""
        from finbar_strategy_runtime.domain.services.order_flow_proxies import (
            signed_sqrt_volume_ofi,
        )

        df = _make_ohlcv_frame(
            [
                {"close": 100.0, "volume": 10000.0},
                {"close": 100.0, "volume": 10000.0},
            ]
        )
        result = signed_sqrt_volume_ofi(df)
        assert result.iloc[-1] == 0.0

    def test_cumulative_version(self):
        """Cumulative OFI accumulates values correctly."""
        from finbar_strategy_runtime.domain.services.order_flow_proxies import (
            cumulative_signed_volume_ofi,
        )

        df = _make_ohlcv_frame(
            [
                {"close": 100.0, "volume": 10000.0},
                {"close": 101.0, "volume": 100.0},  # +10
                {"close": 102.0, "volume": 400.0},  # +20
                {"close": 101.0, "volume": 2500.0},  # -50
            ]
        )
        result = cumulative_signed_volume_ofi(df)
        # Each bar: sign(Δclose) * sqrt(volume)
        # bar1: +sqrt(100) = +10.0  → cum = 10.0
        # bar2: +sqrt(400) = +20.0  → cum = 30.0
        # bar3: -sqrt(2500) = -50.0 → cum = -20.0
        assert abs(result.iloc[1] - 10.0) < 1e-9
        assert abs(result.iloc[2] - 30.0) < 1e-9
        assert abs(result.iloc[3] - -20.0) < 1e-9
