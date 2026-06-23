"""Contract tests for microstructure proxies — round 3 (final batch).

Covers: remaining volatility, liquidity, intraday seasonality,
order arrival, information share.
"""

import numpy as np
import pandas as pd

# =========================================================================
# Volatility (remaining)
# =========================================================================


class TestRemainingVolatility:
    def test_gk_plus_overnight_vol(self):
        from finbar_strategy_runtime.domain.services.volatility_estimators import (
            gk_plus_overnight_vol,
        )

        np.random.seed(10)
        periods = 40
        close = 100 + np.cumsum(np.random.randn(periods) * 0.5)
        df = pd.DataFrame(
            {
                "open": close - np.random.rand(periods) * 0.3,
                "high": close + np.random.rand(periods) * 0.5,
                "low": close - np.random.rand(periods) * 0.5,
                "close": close,
            }
        )
        result = gk_plus_overnight_vol(df)
        assert (result.dropna() >= 0).all()

    def test_meilijson_vol(self):
        from finbar_strategy_runtime.domain.services.volatility_estimators import (
            meilijson_vol,
        )

        np.random.seed(11)
        periods = 40
        close = 100 + np.cumsum(np.random.randn(periods) * 0.5)
        df = pd.DataFrame(
            {
                "open": close - np.random.rand(periods) * 0.3,
                "high": close + np.random.rand(periods) * 0.5,
                "low": close - np.random.rand(periods) * 0.5,
                "close": close,
            }
        )
        result = meilijson_vol(df)
        assert (result.dropna() >= 0).all()

    def test_daily_return_skewness(self):
        from finbar_strategy_runtime.domain.services.volatility_estimators import (
            daily_return_skewness,
        )

        close = pd.Series(100 + np.arange(80) * 0.2)
        result = daily_return_skewness(close)
        assert not pd.isna(result.iloc[-1])

    def test_daily_return_kurtosis(self):
        from finbar_strategy_runtime.domain.services.volatility_estimators import (
            daily_return_kurtosis,
        )

        close = pd.Series(100 + np.arange(80) * 0.2)
        result = daily_return_kurtosis(close)
        assert not pd.isna(result.iloc[-1])


# =========================================================================
# Liquidity (remaining)
# =========================================================================


class TestRemainingLiquidity:
    def test_hasbrouck_daily_lambda(self):
        from finbar_strategy_runtime.domain.services.liquidity_proxies import (
            hasbrouck_daily_lambda,
        )

        np.random.seed(12)
        periods = 40
        close = 100 + np.cumsum(np.random.randn(periods) * 0.5)
        df = pd.DataFrame(
            {
                "close": close,
                "volume": np.random.randint(1000, 100000, periods).astype(float),
            }
        )
        result = hasbrouck_daily_lambda(df)
        assert (result.dropna() >= 0).all()

    def test_liu_illiq(self):
        from finbar_strategy_runtime.domain.services.liquidity_proxies import (
            liu_illiq,
        )

        volume = pd.Series([0.0, 1000.0] * 15 + [1000.0])  # 31 bars, half zero
        result = liu_illiq(volume)
        assert 0.0 <= result <= 1.0

    def test_turnover_positive(self):
        from finbar_strategy_runtime.domain.services.liquidity_proxies import (
            turnover,
        )

        volume = pd.Series([10000.0] * 30)
        result = turnover(volume, shares_outstanding=1_000_000)
        assert (result.dropna() > 0).all()

    def test_bao_pan_zhou_cost(self):
        from finbar_strategy_runtime.domain.services.liquidity_proxies import (
            bao_pan_zhou_cost,
        )

        np.random.seed(13)
        close = pd.Series(100 + np.cumsum(np.random.randn(40) * 0.5))
        result = bao_pan_zhou_cost(close)
        assert result >= 0


# =========================================================================
# Intraday seasonality
# =========================================================================


class TestIntradaySeasonality:
    def test_overnight_intraday_decomp(self):
        from finbar_strategy_runtime.domain.services.intraday_seasonality_proxies import (
            overnight_intraday_decomp,
        )

        np.random.seed(14)
        periods = 40
        close = 100 + np.cumsum(np.random.randn(periods) * 0.5)
        df = pd.DataFrame(
            {
                "open": close - np.random.rand(periods) * 0.3,
                "high": close + np.random.rand(periods) * 0.5,
                "low": close - np.random.rand(periods) * 0.5,
                "close": close,
            }
        )
        overnight, intraday = overnight_intraday_decomp(df)
        assert len(overnight) == len(df)
        assert len(intraday) == len(df)

    def test_parametric_u_shape(self):
        from finbar_strategy_runtime.domain.services.intraday_seasonality_proxies import (
            parametric_u_shape,
        )

        volume = pd.Series(np.random.randint(1000, 100000, 78).astype(float))
        result = parametric_u_shape(volume, bars_per_day=78)
        assert len(result) == 78
        assert (result >= 0).all()


# =========================================================================
# Order arrival
# =========================================================================


class TestOrderArrival:
    def test_volume_to_trade_count_proxy(self):
        from finbar_strategy_runtime.domain.services.order_arrival_proxies import (
            volume_to_trade_count_proxy,
        )

        volume = pd.Series([10000.0] * 30)
        result = volume_to_trade_count_proxy(volume, avg_trade_size=500.0)
        assert (result >= 0).all()
        # 10000 / 500 = 20 trades
        assert result.iloc[-1] == 20.0


# =========================================================================
# Information share
# =========================================================================


class TestInformationShare:
    def test_cross_price_leadership(self):
        from finbar_strategy_runtime.domain.services.information_share_proxies import (
            cross_price_leadership,
        )

        np.random.seed(15)
        periods = 80
        asset_a = pd.Series(100 + np.cumsum(np.random.randn(periods) * 0.5))
        asset_b = pd.Series(100 + np.cumsum(np.random.randn(periods) * 0.5))
        result = cross_price_leadership(asset_a, asset_b)
        # Difference of two correlations is in [-2, 2]
        assert -2.0 <= result <= 2.0

    def test_cross_price_leadership_detects_lead(self):
        """When A leads B by 1 lag, the score should be positive."""
        from finbar_strategy_runtime.domain.services.information_share_proxies import (
            cross_price_leadership,
        )

        np.random.seed(42)
        n = 200
        ret_a = pd.Series(np.random.randn(n) * 0.02)
        ret_b = pd.Series(np.zeros(n))
        for i in range(1, n):
            ret_b.iloc[i] = 0.8 * ret_a.iloc[i - 1] + np.random.randn() * 0.005
        price_a = (1 + ret_a).cumprod()
        price_b = (1 + ret_b).cumprod()

        score = cross_price_leadership(price_a, price_b, lookback=100)
        assert score > 0.5, f"Expected A to lead B, got score={score:.4f}"

    def test_volume_weighted_is(self):
        from finbar_strategy_runtime.domain.services.information_share_proxies import (
            volume_weighted_is,
        )

        volume_a = pd.Series([10000.0] * 30)
        volume_b = pd.Series([5000.0] * 30)
        result = volume_weighted_is(volume_a, volume_b)
        # Asset A has 2x volume → IS ≈ 0.667
        assert result > 0.6

    def test_opening_price_leadership(self):
        from finbar_strategy_runtime.domain.services.information_share_proxies import (
            opening_price_leadership,
        )

        np.random.seed(16)
        periods = 80
        open_a = pd.Series(100 + np.cumsum(np.random.randn(periods) * 0.5))
        open_b = pd.Series(100 + np.cumsum(np.random.randn(periods) * 0.5))
        result = opening_price_leadership(open_a, open_b)
        assert -1.0 <= result <= 1.0

    def test_daily_cross_correlation(self):
        from finbar_strategy_runtime.domain.services.information_share_proxies import (
            daily_cross_correlation,
        )

        np.random.seed(17)
        periods = 80
        close_a = pd.Series(100 + np.cumsum(np.random.randn(periods) * 0.5))
        close_b = pd.Series(100 + np.cumsum(np.random.randn(periods) * 0.5))
        result = daily_cross_correlation(close_a, close_b)
        assert not pd.isna(result.iloc[-1])
        assert -1.0 <= result.iloc[-1] <= 1.0

    def test_daily_beta_ols(self):
        from finbar_strategy_runtime.domain.services.information_share_proxies import (
            daily_beta_ols,
        )

        np.random.seed(18)
        periods = 80
        benchmark = pd.Series(100 + np.cumsum(np.random.randn(periods) * 0.5))
        # Asset with beta ≈ 1.5 relative to benchmark
        asset = pd.Series(100 + np.cumsum(np.random.randn(periods) * 0.75 + benchmark.pct_change().fillna(0) * 1.5))
        result = daily_beta_ols(asset, benchmark)
        assert not pd.isna(result.iloc[-1])
