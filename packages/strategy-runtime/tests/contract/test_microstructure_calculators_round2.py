"""Contract tests for additional microstructure proxy calculators — round 2.

Covers: spread (effective_tick, lot_zero_return), return_vol_corr,
informed trading (daily_vpin), jump risk, resiliency.
"""

import numpy as np
import pandas as pd
import pytest


def _make_ohlcv_frame(data: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(data)


# =========================================================================
# Spread proxies (remaining)
# =========================================================================


class TestEffectiveTickSpread:
    """Holden (2009): close-to-close price clustering spread."""

    def test_returns_float_series(self):
        from finbar_strategy_runtime.domain.services.spread_proxies import (
            effective_tick_spread,
        )

        np.random.seed(5)
        periods = 100
        close = pd.Series(100 + np.cumsum(np.random.randn(periods) * 0.5))
        result = effective_tick_spread(close)
        assert result >= 0
        assert isinstance(result, float) or isinstance(result, np.floating)


class TestLotZeroReturnSpread:
    """LOT (1999): zero-return proportion spread."""

    def test_all_nonzero_returns_zero_spread(self):
        from finbar_strategy_runtime.domain.services.spread_proxies import (
            lot_zero_return_spread,
        )

        close = pd.Series(100.0 + np.arange(70) * 0.5)
        result = lot_zero_return_spread(close)
        assert result == 0.0

    def test_insufficient_bars_returns_none(self):
        from finbar_strategy_runtime.domain.services.spread_proxies import (
            lot_zero_return_spread,
        )

        close = pd.Series([100.0, 101.0])
        result = lot_zero_return_spread(close)
        assert result is None


# =========================================================================
# Return-volume correlation
# =========================================================================


class TestReturnVolumeCorrelation:
    """Correlation between |returns| and volume."""

    def test_known_pattern(self):
        from finbar_strategy_runtime.domain.services.order_flow_proxies import (
            return_volume_correlation,
        )

        np.random.seed(7)
        periods = 80
        close = pd.Series(100 + np.cumsum(np.random.randn(periods)))
        volume = pd.Series(np.random.randint(1000, 100000, periods).astype(float))
        df = pd.DataFrame({"close": close, "volume": volume})
        result = return_volume_correlation(df)
        # Rolling correlation of abs(ret) and volume
        assert not pd.isna(result.iloc[-1])
        assert -1.0 <= result.iloc[-1] <= 1.0

    def test_min_lookback_respected(self):
        from finbar_strategy_runtime.domain.services.order_flow_proxies import (
            return_volume_correlation,
        )

        close = pd.Series([100.0, 101.0, 102.0] * 5)
        volume = pd.Series([1000.0] * 15)
        df = pd.DataFrame({"close": close, "volume": volume})
        result = return_volume_correlation(df, lookback=60)
        assert result.isna().all()


# =========================================================================
# Informed trading proxies
# =========================================================================


class TestDailyVpin:
    """ELO (2012): daily VPIN — volume-synchronized PIN proxy."""

    def test_output_within_0_1(self):
        from finbar_strategy_runtime.domain.services.informed_trading_proxies import (
            daily_vpin,
        )

        np.random.seed(9)
        periods = 80
        close = pd.Series(100 + np.cumsum(np.random.randn(periods)))
        volume = pd.Series(np.random.randint(1000, 100000, periods).astype(float))
        df = pd.DataFrame({"close": close, "volume": volume})
        result = daily_vpin(df)
        # VPIN is a probability — should be in [0, 1]
        assert (result.dropna() >= 0).all()
        assert (result.dropna() <= 1).all()

    def test_insufficient_bars_returns_nan(self):
        from finbar_strategy_runtime.domain.services.informed_trading_proxies import (
            daily_vpin,
        )

        close = pd.Series([100.0] * 10)
        volume = pd.Series([1000.0] * 10)
        df = pd.DataFrame({"close": close, "volume": volume})
        result = daily_vpin(df, lookback=50)
        assert result.isna().all()


# =========================================================================
# Jump / tail risk proxies
# =========================================================================


class TestJumpRiskProxies:
    """Jump and tail risk proxy calculators."""

    def test_jump_gap_proxy_positive_on_gap(self):
        from finbar_strategy_runtime.domain.services.jump_risk_proxies import (
            jump_gap_proxy,
        )

        df = _make_ohlcv_frame(
            [
                {"open": 95.0, "high": 96.0, "low": 94.0, "close": 95.5},
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
            ]
            * 25
        )
        result = jump_gap_proxy(df)
        assert (result.dropna() >= 0).all()

    def test_extreme_return_flag(self):
        from finbar_strategy_runtime.domain.services.jump_risk_proxies import (
            extreme_return_flag,
        )

        close = pd.Series(100.0 + np.arange(50) * 0.1)  # 50 bars
        close.iloc[30] = 200.0  # extreme jump at bar 30 (after lookback)
        result = extreme_return_flag(close, lookback=20, n_sigma=3.0)
        assert result.iloc[30] == True

    def test_overnight_gap_proxy(self):
        from finbar_strategy_runtime.domain.services.jump_risk_proxies import (
            overnight_gap_proxy,
        )

        df = _make_ohlcv_frame(
            [
                {"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0},
                {"open": 95.0, "high": 96.0, "low": 94.0, "close": 95.5},
            ]
            * 25
        )
        result = overnight_gap_proxy(df)
        assert (result.dropna() >= 0).all()


# =========================================================================
# Resiliency proxies
# =========================================================================


class TestResiliencyProxies:
    """Resiliency proxy calculators."""

    def test_resiliency_autocorr_in_range(self):
        from finbar_strategy_runtime.domain.services.resiliency_proxies import (
            resiliency_autocorr,
        )

        np.random.seed(11)
        close = pd.Series(100 + np.cumsum(np.random.randn(50) * 0.5))
        result = resiliency_autocorr(close)
        assert -1.0 <= result <= 1.0

    def test_inverse_amihud_resiliency(self):
        from finbar_strategy_runtime.domain.services.resiliency_proxies import (
            inverse_amihud_resiliency,
        )

        np.random.seed(13)
        periods = 40
        close = pd.Series(100 + np.cumsum(np.random.randn(periods) * 0.5))
        volume = pd.Series(np.random.randint(1000, 100000, periods).astype(float))
        df = pd.DataFrame({"close": close, "volume": volume})
        result = inverse_amihud_resiliency(df)
        # Inverse Amihud → larger = more resilient
        assert (result.dropna() >= 0).all()
