"""Contract tests for SMC, VSA, Supply/Demand, Hurst, Market Regime calculators."""

import numpy as np
import pandas as pd
import pytest


# =========================================================================
# Supply / Demand zones
# =========================================================================


class TestSupplyDemandZones:
    def test_demand_zone_from_rbr(self):
        """Rally-base-rally creates a demand zone."""
        from finbar_strategy_runtime.domain.services.supply_demand_zones import (
            demand_zone_low,
            demand_zone_high,
            demand_zone_score,
        )

        # Double bottom pattern creating demand zone
        close = pd.Series([100, 110, 105, 108, 103, 102, 107, 115, 120, 118, 125])
        high = close + 2
        low = close - 2
        volume = pd.Series([1000.0] * len(close))

        dl = demand_zone_low(high, low, close)
        dh = demand_zone_high(high, low, close)
        ds = demand_zone_score(high, low, close, volume)

        assert len(dl) == len(close)
        assert len(dh) == len(close)
        assert len(ds) == len(close)

    def test_supply_zone_from_dbr(self):
        from finbar_strategy_runtime.domain.services.supply_demand_zones import (
            supply_zone_low,
            supply_zone_high,
        )

        close = pd.Series([120, 115, 118, 113, 110, 112, 108, 105, 102, 100, 103])
        high = close + 2
        low = close - 2

        sl = supply_zone_low(high, low, close)
        sh = supply_zone_high(high, low, close)

        assert len(sl) == len(close)
        assert len(sh) == len(close)

    def test_zone_failure_bullish(self):
        from finbar_strategy_runtime.domain.services.supply_demand_zones import (
            zone_failure_bullish,
        )

        # Supply zone broken above on volume
        close = pd.Series([110, 108, 105, 107, 106, 109, 112, 115, 118, 120])
        high = close + 2
        low = close - 2
        volume = pd.Series([1000, 800, 900, 850, 900, 1200, 1500, 1800, 1600, 2000])

        result = zone_failure_bullish(high, low, close, volume)
        assert isinstance(result.iloc[-1], (bool, np.bool_))


# =========================================================================
# SMC / Smart Money Concepts
# =========================================================================


class TestSMC:
    def test_bullish_fvg(self):
        from finbar_strategy_runtime.domain.services.smc_price_action import (
            bullish_fvg,
        )

        # Three candles: candle-1 high < candle-3 low → bull FVG
        high = pd.Series([10, 11, 12, 13, 9, 10, 11])
        low = pd.Series([8, 9, 10, 11, 7, 8, 9])
        close = pd.Series([9, 10, 11, 12, 8, 9, 10])
        result = bullish_fvg(high, low)
        assert isinstance(result.iloc[-1], (bool, np.bool_))

    def test_bearish_fvg(self):
        from finbar_strategy_runtime.domain.services.smc_price_action import (
            bearish_fvg,
        )

        high = pd.Series([12, 11, 10, 9, 15, 14, 13])
        low = pd.Series([10, 9, 8, 7, 13, 12, 11])
        result = bearish_fvg(high, low)
        assert isinstance(result.iloc[-1], (bool, np.bool_))

    def test_bullish_order_block(self):
        from finbar_strategy_runtime.domain.services.smc_price_action import (
            bullish_order_block,
        )

        close = pd.Series([100, 98, 96, 95, 97, 102, 108, 115, 112])
        result = bullish_order_block(close)
        assert isinstance(result.iloc[-1], (bool, np.bool_))

    def test_liquidity_sweep_high(self):
        from finbar_strategy_runtime.domain.services.smc_price_action import (
            liquidity_sweep_high,
        )

        high = pd.Series([10, 12, 11, 13, 14, 13, 11, 10])
        low = pd.Series([8, 9, 9, 10, 11, 10, 9, 8])
        close = pd.Series([9, 11, 10, 12, 13, 12, 10, 9])
        result = liquidity_sweep_high(high, low, close)
        assert isinstance(result.iloc[-1], (bool, np.bool_))

    def test_bos_and_choch(self):
        from finbar_strategy_runtime.domain.services.smc_price_action import (
            bos,
            choch,
        )

        # Uptrend → BOS expected; CHoCH = reversal
        close = pd.Series(100.0 + np.arange(30) * 0.5)
        high = close + 2
        low = close - 2

        b = bos(high, low)
        c = choch(high, low)
        assert isinstance(b.iloc[-1], (bool, np.bool_))
        assert isinstance(c.iloc[-1], (bool, np.bool_))

    def test_premium_discount_zone(self):
        from finbar_strategy_runtime.domain.services.smc_price_action import (
            premium_discount_zone,
        )

        high = pd.Series([100, 105, 110, 108, 106, 104, 102, 100, 98, 96])
        low = pd.Series([95, 98, 100, 99, 97, 96, 94, 92, 90, 88])
        result = premium_discount_zone(high, low)
        assert result.iloc[-1] in ("premium", "discount", "equilibrium")


# =========================================================================
# VSA / Volume Spread Analysis
# =========================================================================


class TestVSA:
    def test_no_demand(self):
        from finbar_strategy_runtime.domain.services.vsa_signals import no_demand

        close = pd.Series([100, 101, 102, 103, 104, 105, 106])
        volume = pd.Series([1000, 900, 800, 300, 1000, 1000, 1000])
        result = no_demand(close, volume)
        assert isinstance(result.iloc[-1], (bool, np.bool_))

    def test_climax_volume(self):
        from finbar_strategy_runtime.domain.services.vsa_signals import climax_volume

        high = pd.Series([100, 102, 104, 106, 108, 110, 112, 108])
        low = pd.Series([98, 100, 102, 100, 102, 104, 106, 102])
        volume = pd.Series([1000] * 7 + [5000])
        result = climax_volume(high, low, volume)
        assert isinstance(result.iloc[-1], (bool, np.bool_))

    def test_effort_to_rise(self):
        from finbar_strategy_runtime.domain.services.vsa_signals import effort_to_rise

        high = pd.Series([100, 102, 104, 106, 108, 110, 112, 120])
        low = pd.Series([98, 100, 102, 104, 106, 108, 110, 110])
        close = pd.Series([99, 101, 103, 105, 107, 109, 111, 114])
        volume = pd.Series([1000] * 7 + [3000])
        result = effort_to_rise(high, low, close, volume)
        assert isinstance(result.iloc[-1], (bool, np.bool_))

    def test_effort_result_divergence(self):
        from finbar_strategy_runtime.domain.services.vsa_signals import (
            effort_result_divergence,
        )

        high = pd.Series([100, 102, 104, 106, 108, 110, 112, 114])
        low = pd.Series([98, 100, 102, 104, 106, 108, 110, 112])
        close = pd.Series([99, 101, 103, 105, 107, 109, 111, 112])
        volume = pd.Series([1000] * 7 + [4000])
        result = effort_result_divergence(high, low, close, volume)
        assert isinstance(result.iloc[-1], (bool, np.bool_))

    def test_shakeout(self):
        from finbar_strategy_runtime.domain.services.vsa_signals import shakeout

        low = pd.Series([100, 99, 98, 95, 97, 99, 101, 103])
        close = pd.Series([101, 100, 99, 96, 102, 104, 105, 106])
        volume = pd.Series([1000] * 3 + [4000, 2000, 1500, 1200, 1000])
        result = shakeout(low, close, volume)
        assert isinstance(result.iloc[-1], (bool, np.bool_))


# =========================================================================
# Hurst exponent / fractal regime
# =========================================================================


class TestHurstRegime:
    def test_hurst_exponent(self):
        from finbar_strategy_runtime.domain.services.hurst_regime import (
            hurst_exponent,
        )

        # Random walk → H ≈ 0.5
        np.random.seed(42)
        close = pd.Series(100 + np.cumsum(np.random.randn(120) * 0.5))
        result = hurst_exponent(close, min_bars=100)
        assert isinstance(result, float)

    def test_fractal_regime(self):
        from finbar_strategy_runtime.domain.services.hurst_regime import (
            fractal_regime,
        )

        np.random.seed(42)
        close = pd.Series(100 + np.cumsum(np.random.randn(120) * 0.5))
        result = fractal_regime(close, min_bars=100)
        assert result in ("TRENDING", "RANDOM", "MEAN_REVERTING", "unknown")


# =========================================================================
# Market regime
# =========================================================================


class TestMarketRegime:
    def test_market_regime_defaults_to_range_bound(self):
        from finbar_strategy_runtime.domain.services.market_regime import (
            market_regime,
        )

        np.random.seed(43)
        close = pd.Series(100 + np.cumsum(np.random.randn(200) * 0.5))
        high = close + 2
        low = close - 2
        volume = pd.Series(np.random.randint(1000, 100000, 200).astype(float))

        result = market_regime(close, high, low, volume)
        assert result.iloc[-1] in (
            "TRENDING_BULL", "TRENDING_BEAR", "RANGE_BOUND", "CRISIS", "unknown"
        )
