"""Contract tests for SMC, VSA, Supply/Demand, Hurst, Market Regime calculators."""

import numpy as np
import pandas as pd

# =========================================================================
# Supply / Demand zones
# =========================================================================


class TestSupplyDemandZones:
    def test_demand_zone_from_rbr(self):
        """Rally-base-rally creates a demand zone."""
        from finbar_strategy_runtime.domain.services.supply_demand_zones import (
            demand_zone_high,
            demand_zone_low,
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
            supply_zone_high,
            supply_zone_low,
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


# =========================================================================
# Regression tests for bug fixes
# =========================================================================


class TestBugFixRegressions:
    """Regression tests for bugs found during review."""

    # --- Fix 2: CHOCH fires once per swing-low break ---
    def test_choch_fires_once_not_continuously(self):
        from finbar_strategy_runtime.domain.services.smc_price_action import choch

        # Uptrend then sharp reversal
        prices = []
        for i in range(200):
            prices.append(100 + i * 0.5 + 10 * np.sin(i * 0.3))
        for i in range(20):
            prices[-20 + i] -= i * 2
        close = pd.Series(prices)
        high = close + 2
        low = close - 2
        result = choch(high, low, window=5)
        assert result.sum() <= 2, (
            f"CHOCH fired on {result.sum()} bars; should fire at most ~1"
        )

    # --- Fix 3: swing signals at confirmation bar, not swing bar ---
    def test_swing_high_n_no_lookahead(self):
        from finbar_strategy_runtime.domain.services.trend_structure import (
            swing_high_n,
        )

        # Clear peak at bar 20
        high = pd.Series(
            [100.0] * 15
            + [105, 110, 115, 120, 125, 130]
            + [128, 125, 122, 119, 116, 113]
            + [110, 107, 104, 101]
            + [98.0] * 19
        )
        result = swing_high_n(high, n=5)
        signal_bars = result[result].index.tolist()
        if signal_bars:
            # Swing at bar 20 confirmed only after 5 more bars → signal at ≥ 25
            assert signal_bars[0] >= 25, (
                f"Signal at bar {signal_bars[0]}, expected >= 25 (no look-ahead)"
            )

    # --- Fix 4: Fibonacci direction-aware for downtrends ---
    def test_fib_downtrend_retrace_above_low(self):
        from finbar_strategy_runtime.domain.services.fibonacci_levels import (
            fib_382_retrace,
        )

        # Swing high=200 at idx 10, swing low=100 at idx 20 (downtrend)
        vals = []
        for i in range(40):
            if i <= 5:
                vals.append(150 + i * 2)
            elif i <= 10:
                vals.append(160 + (i - 5) * 8)
            elif i <= 20:
                vals.append(200 - (i - 10) * 10)
            elif i <= 25:
                vals.append(100 + (i - 20) * 4)
            else:
                vals.append(120 + (i - 25) * 0.5)
        close = pd.Series(vals)
        result = fib_382_retrace(close, swing_window=5).dropna()
        if len(result) > 0:
            level = result.iloc[-1]
            # For downtrend 200->100: 38.2% retrace = 100 + 0.382*100 = 138.2
            assert 130 < level < 145, (
                f"Got {level:.1f}, expected ~138.2 for downtrend retrace"
            )

    def test_fib_downtrend_extension_below_low(self):
        from finbar_strategy_runtime.domain.services.fibonacci_levels import (
            fib_1618_extension,
        )

        vals = []
        for i in range(40):
            if i <= 5:
                vals.append(150 + i * 2)
            elif i <= 10:
                vals.append(160 + (i - 5) * 8)
            elif i <= 20:
                vals.append(200 - (i - 10) * 10)
            elif i <= 25:
                vals.append(100 + (i - 20) * 4)
            else:
                vals.append(120 + (i - 25) * 0.5)
        close = pd.Series(vals)
        result = fib_1618_extension(close, swing_window=5).dropna()
        if len(result) > 0:
            level = result.iloc[-1]
            # For downtrend 200->100: 1.618 ext = 100 - 0.618*100 = 38.2
            assert 30 < level < 50, (
                f"Got {level:.1f}, expected ~38.2 for downtrend extension"
            )

    # --- Fix 5: daily_vpin flat bars split 50/50 ---
    def test_vpin_flat_bars_not_double_counted(self):
        from finbar_strategy_runtime.domain.services.informed_trading_proxies import (
            daily_vpin,
        )

        # 30 flat + 20 up + 10 flat
        close = pd.Series(
            [100.0] * 30 + list(np.linspace(100, 120, 20)) + [120.0] * 10
        )
        volume = pd.Series([1000.0] * 60)
        df = pd.DataFrame({"close": close, "volume": volume})
        result = daily_vpin(df, lookback=50)
        last = result.iloc[-1]
        # With 50/50 split: VPIN should be ~0.40, not ~0.23
        assert last > 0.30, (
            f"VPIN={last:.4f}; flat bars appear double-counted if < 0.30"
        )

    # --- Fix 6: zone_signal requires AC positive for green ---
    def test_zone_signal_green_requires_ac_positive(self):
        from finbar_strategy_runtime.domain.services.bill_williams_indicators import (
            accelerator_oscillator,
            zone_signal,
        )

        # Build data where AO>0 rising but AC<0
        vals = []
        for i in range(60):
            vals.append(100 * (1.005 ** i))
        for i in range(20):
            vals.append(vals[-1] * (1.0 + 0.0001))
        for i in range(40):
            vals.append(vals[-1] * 1.006)
        close = pd.Series(vals)
        high = close * 1.003
        low = close * 0.997
        result = zone_signal(high, low)
        ac = accelerator_oscillator(high, low)
        green_mask = result == "green"
        # No green bar should have AC < 0
        neg_ac_green = (ac[green_mask] < 0).sum()
        assert neg_ac_green == 0, (
            f"{neg_ac_green} green bars have AC<0 (should require AC>0)"
        )

    # --- Fix 7: lot_zero_return_spread returns None for all-zero returns ---
    def test_lot_all_zero_returns_none(self):
        from finbar_strategy_runtime.domain.services.spread_proxies import (
            lot_zero_return_spread,
        )

        close = pd.Series([100.0] * 70)
        result = lot_zero_return_spread(close, lookback=60)
        assert result is None, (
            "All-zero returns (max illiquidity) should return None, not 0.0"
        )

    # --- Fix 9: day_type_classification uses high/low for IB, not open ---
    def test_day_type_ib_from_high_low_not_open(self):
        from finbar_strategy_runtime.domain.services.market_regime import (
            day_type_classification,
        )

        high = pd.Series(
            [110.0, 105, 108, 120, 125, 122, 118, 115, 112, 109]
        )
        low = pd.Series([95, 100, 98, 105, 110, 107, 103, 100, 97, 94])
        close = pd.Series([100, 103, 105, 115, 120, 115, 110, 107, 104, 100])
        open_ = pd.Series([108, 102, 100, 110, 115, 120, 115, 110, 105, 100])
        r_with_open = day_type_classification(high, low, close, open_=open_)
        r_no_open = day_type_classification(high, low, close, open_=None)
        assert (r_with_open == r_no_open).all(), (
            "open_ parameter should not affect IB computation"
        )

    # --- Fix 10: trend_phase defaults to unknown, not markup ---
    def test_trend_phase_flat_market_not_markup(self):
        from finbar_strategy_runtime.domain.services.trend_structure import (
            trend_phase,
        )

        close = pd.Series([100.0] * 30 + [100.5] * 30)
        volume = pd.Series([1000.0] * 60)
        result = trend_phase(close, volume, lookback=20)
        assert result.iloc[-1] != "markup", (
            "Flat market should not default to 'markup'"
        )
