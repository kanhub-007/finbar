"""Price-action handlers — Fibonacci, Bill Williams, SMC, VSA, zones, regime.

This module is imported by ``handlers/__init__.py`` which triggers
registration of all ``@_register`` decorators at import time.
"""

import pandas as pd

from finbar_strategy_runtime.indicators._handler_registry import _register


from finbar_strategy_runtime.domain.services.fibonacci_levels import (  # noqa: E402
    fib_1618_extension as _fib_ext,
    fib_382_retrace as _fib382,
    fib_500_retrace as _fib500,
    fib_618_retrace as _fib618,
    fib_confluence_score as _fib_conf,
)
from finbar_strategy_runtime.domain.services.bill_williams_indicators import (  # noqa: E402
    accelerator_oscillator as _ac_osc,
    alligator_lines as _alig_lines,
    alligator_status as _alig_status,
    awesome_oscillator as _ao_osc,
    williams_fractal_high as _frac_high,
    williams_fractal_low as _frac_low,
    zone_signal as _bw_zone,
)
from finbar_strategy_runtime.domain.services.trend_structure import (  # noqa: E402
    hh_hl_pattern as _hh_hl,
    lh_ll_pattern as _lh_ll,
    swing_high_n as _swing_h,
    swing_low_n as _swing_l,
    trend_phase as _trend_phase,
    volume_trend_confirmation as _vol_trend,
)
from finbar_strategy_runtime.domain.services.smc_price_action import (  # noqa: E402
    bearish_fvg as _bear_fvg,
    bearish_order_block as _bear_ob,
    bos as _bos,
    breaker_block_bearish as _breaker_bear,
    breaker_block_bullish as _breaker_bull,
    bullish_fvg as _bull_fvg,
    bullish_order_block as _bull_ob,
    choch as _choch,
    liquidity_sweep_high as _sweep_high,
    liquidity_sweep_low as _sweep_low,
    premium_discount_zone as _pd_zone,
)
from finbar_strategy_runtime.domain.services.vsa_signals import (  # noqa: E402
    bag_holding as _bag_hold,
    climax_volume as _climax,
    effort_result_divergence as _er_div,
    effort_to_fall as _eff_fall,
    effort_to_rise as _eff_rise,
    no_demand as _no_dem,
    no_supply as _no_sup,
    shakeout as _shakeout,
    stopping_volume as _stop_vol,
    vsa_test_signal as _vsa_test,
)
from finbar_strategy_runtime.domain.services.supply_demand_zones import (  # noqa: E402
    demand_zone_high as _dz_high,
    demand_zone_low as _dz_low,
    demand_zone_score as _dz_score,
    supply_zone_high as _sz_high,
    supply_zone_low as _sz_low,
    supply_zone_score as _sz_score,
    zone_failure_bearish as _zf_bear,
    zone_failure_bullish as _zf_bull,
)
from finbar_strategy_runtime.domain.services.hurst_regime import (  # noqa: E402
    fractal_regime as _frac_regime,
    hurst_exponent as _hurst,
)
from finbar_strategy_runtime.domain.services.market_regime import (  # noqa: E402
    day_type_classification as _day_type,
    market_regime as _mkt_regime,
)
from finbar_strategy_runtime.indicators.rolling_scalar_wrapper import (  # noqa: E402
    broadcast_scalar_over_series,
)


# --- Fibonacci (5) ---

@_register("fib_382_retrace", requires={"close"})
def _h_fib382(df, _name, _cache):
    df["fib_382_retrace"] = _fib382(df["close"])
    return df

@_register("fib_500_retrace", requires={"close"})
def _h_fib500(df, _name, _cache):
    df["fib_500_retrace"] = _fib500(df["close"])
    return df

@_register("fib_618_retrace", requires={"close"})
def _h_fib618(df, _name, _cache):
    df["fib_618_retrace"] = _fib618(df["close"])
    return df

@_register("fib_1618_extension", requires={"close"})
def _h_fib_ext(df, _name, _cache):
    df["fib_1618_extension"] = _fib_ext(df["close"])
    return df

@_register("fib_confluence_score", requires={"close"})
def _h_fib_conf(df, _name, _cache):
    df["fib_confluence_score"] = _fib_conf(df["close"])
    return df


# --- Bill Williams (9: 6 single + alligator 3) ---

@_register("awesome_oscillator", requires={"high", "low"})
def _h_ao(df, _name, _cache):
    df["awesome_oscillator"] = _ao_osc(df["high"], df["low"])
    return df

@_register("accelerator_oscillator", requires={"high", "low"})
def _h_ac(df, _name, _cache):
    df["accelerator_oscillator"] = _ac_osc(df["high"], df["low"])
    return df

@_register("alligator_jaw", requires={"high", "low"})
def _h_alig_jaw(df, _name, _cache):
    jaw, _teeth, _lips = _alig_lines(df["high"], df["low"])
    df["alligator_jaw"] = jaw
    return df

@_register("alligator_teeth", requires={"high", "low"})
def _h_alig_teeth(df, _name, _cache):
    _jaw, teeth, _lips = _alig_lines(df["high"], df["low"])
    df["alligator_teeth"] = teeth
    return df

@_register("alligator_lips", requires={"high", "low"})
def _h_alig_lips(df, _name, _cache):
    _jaw, _teeth, lips = _alig_lines(df["high"], df["low"])
    df["alligator_lips"] = lips
    return df

@_register("alligator_status", requires={"high", "low"})
def _h_alig_status(df, _name, _cache):
    jaw, teeth, lips = _alig_lines(df["high"], df["low"])
    df["alligator_status"] = _alig_status(jaw, teeth, lips)
    return df

@_register("williams_fractal_high", requires={"high"})
def _h_frac_high(df, _name, _cache):
    df["williams_fractal_high"] = _frac_high(df["high"])
    return df

@_register("williams_fractal_low", requires={"low"})
def _h_frac_low(df, _name, _cache):
    df["williams_fractal_low"] = _frac_low(df["low"])
    return df

@_register("zone_signal", requires={"high", "low"})
def _h_bw_zone(df, _name, _cache):
    df["zone_signal"] = _bw_zone(df["high"], df["low"])
    return df


# --- Trend structure (6) ---

@_register("swing_high_n", requires={"high"})
def _h_swing_h(df, _name, _cache):
    df["swing_high_n"] = _swing_h(df["high"])
    return df

@_register("swing_low_n", requires={"low"})
def _h_swing_l(df, _name, _cache):
    df["swing_low_n"] = _swing_l(df["low"])
    return df

@_register("hh_hl_pattern", requires={"high", "low"})
def _h_hh_hl(df, _name, _cache):
    df["hh_hl_pattern"] = _hh_hl(df["high"], df["low"])
    return df

@_register("lh_ll_pattern", requires={"high", "low"})
def _h_lh_ll(df, _name, _cache):
    df["lh_ll_pattern"] = _lh_ll(df["high"], df["low"])
    return df

@_register("volume_trend_confirmation", requires={"close", "volume"})
def _h_vol_trend(df, _name, _cache):
    df["volume_trend_confirmation"] = _vol_trend(df["close"], df["volume"])
    return df

@_register("trend_phase", requires={"close", "volume"})
def _h_trend_phase(df, _name, _cache):
    df["trend_phase"] = _trend_phase(df["close"], df["volume"])
    return df


# --- SMC (11) ---

@_register("bullish_fvg", requires={"high", "low"})
def _h_bull_fvg(df, _name, _cache):
    df["bullish_fvg"] = _bull_fvg(df["high"], df["low"])
    return df

@_register("bearish_fvg", requires={"high", "low"})
def _h_bear_fvg(df, _name, _cache):
    df["bearish_fvg"] = _bear_fvg(df["high"], df["low"])
    return df

@_register("bullish_order_block", requires={"close"})
def _h_bull_ob(df, _name, _cache):
    df["bullish_order_block"] = _bull_ob(df["close"])
    return df

@_register("bearish_order_block", requires={"close"})
def _h_bear_ob(df, _name, _cache):
    df["bearish_order_block"] = _bear_ob(df["close"])
    return df

@_register("breaker_block_bullish", requires={"high", "low", "close"})
def _h_breaker_bull(df, _name, _cache):
    df["breaker_block_bullish"] = _breaker_bull(df["high"], df["low"], df["close"])
    return df

@_register("breaker_block_bearish", requires={"high", "low", "close"})
def _h_breaker_bear(df, _name, _cache):
    df["breaker_block_bearish"] = _breaker_bear(df["high"], df["low"], df["close"])
    return df

@_register("liquidity_sweep_high", requires={"high", "low", "close"})
def _h_sweep_high(df, _name, _cache):
    df["liquidity_sweep_high"] = _sweep_high(df["high"], df["low"], df["close"])
    return df

@_register("liquidity_sweep_low", requires={"high", "low", "close"})
def _h_sweep_low(df, _name, _cache):
    df["liquidity_sweep_low"] = _sweep_low(df["high"], df["low"], df["close"])
    return df

@_register("bos", requires={"high", "low"})
def _h_bos(df, _name, _cache):
    df["bos"] = _bos(df["high"], df["low"])
    return df

@_register("choch", requires={"high", "low"})
def _h_choch(df, _name, _cache):
    df["choch"] = _choch(df["high"], df["low"])
    return df

@_register("premium_discount_zone", requires={"high", "low"})
def _h_pd_zone(df, _name, _cache):
    df["premium_discount_zone"] = _pd_zone(df["high"], df["low"])
    return df


# --- VSA (10) ---

@_register("no_demand", requires={"close", "volume"})
def _h_no_dem(df, _name, _cache):
    df["no_demand"] = _no_dem(df["close"], df["volume"])
    return df

@_register("no_supply", requires={"close", "volume"})
def _h_no_sup(df, _name, _cache):
    df["no_supply"] = _no_sup(df["close"], df["volume"])
    return df

@_register("stopping_volume", requires={"high", "low", "volume"})
def _h_stop_vol(df, _name, _cache):
    df["stopping_volume"] = _stop_vol(df["high"], df["low"], df["volume"])
    return df

@_register("climax_volume", requires={"high", "low", "volume"})
def _h_climax(df, _name, _cache):
    df["climax_volume"] = _climax(df["high"], df["low"], df["volume"])
    return df

@_register("effort_to_rise", requires={"high", "low", "close", "volume"})
def _h_eff_rise(df, _name, _cache):
    df["effort_to_rise"] = _eff_rise(df["high"], df["low"], df["close"], df["volume"])
    return df

@_register("effort_to_fall", requires={"high", "low", "close", "volume"})
def _h_eff_fall(df, _name, _cache):
    df["effort_to_fall"] = _eff_fall(df["high"], df["low"], df["close"], df["volume"])
    return df

@_register("effort_result_divergence", requires={"high", "low", "close", "volume"})
def _h_er_div(df, _name, _cache):
    df["effort_result_divergence"] = _er_div(df["high"], df["low"], df["close"], df["volume"])
    return df

@_register("bag_holding", requires={"close", "volume"})
def _h_bag_hold(df, _name, _cache):
    df["bag_holding"] = _bag_hold(df["close"], df["volume"])
    return df

@_register("shakeout", requires={"low", "close", "volume"})
def _h_shakeout(df, _name, _cache):
    df["shakeout"] = _shakeout(df["low"], df["close"], df["volume"])
    return df

@_register("vsa_test_signal", requires={"high", "low", "close", "volume"})
def _h_vsa_test(df, _name, _cache):
    df["vsa_test_signal"] = _vsa_test(df["high"], df["low"], df["close"], df["volume"])
    return df


# --- Supply/demand zones (8) ---

@_register("demand_zone_low", requires={"high", "low", "close"})
def _h_dz_low(df, _name, _cache):
    df["demand_zone_low"] = _dz_low(df["high"], df["low"], df["close"])
    return df

@_register("demand_zone_high", requires={"high", "low", "close"})
def _h_dz_high(df, _name, _cache):
    df["demand_zone_high"] = _dz_high(df["high"], df["low"], df["close"])
    return df

@_register("demand_zone_score", requires={"high", "low", "close"})
def _h_dz_score(df, _name, _cache):
    df["demand_zone_score"] = _dz_score(df["high"], df["low"], df["close"])
    return df

@_register("supply_zone_low", requires={"high", "low", "close"})
def _h_sz_low(df, _name, _cache):
    df["supply_zone_low"] = _sz_low(df["high"], df["low"], df["close"])
    return df

@_register("supply_zone_high", requires={"high", "low", "close"})
def _h_sz_high(df, _name, _cache):
    df["supply_zone_high"] = _sz_high(df["high"], df["low"], df["close"])
    return df

@_register("supply_zone_score", requires={"high", "low", "close"})
def _h_sz_score(df, _name, _cache):
    df["supply_zone_score"] = _sz_score(df["high"], df["low"], df["close"])
    return df

@_register("zone_failure_bullish", requires={"high", "low", "close"})
def _h_zf_bull(df, _name, _cache):
    df["zone_failure_bullish"] = _zf_bull(df["high"], df["low"], df["close"])
    return df

@_register("zone_failure_bearish", requires={"high", "low", "close"})
def _h_zf_bear(df, _name, _cache):
    df["zone_failure_bearish"] = _zf_bear(df["high"], df["low"], df["close"])
    return df


# --- Hurst regime (2) ---

@_register("hurst_exponent", requires={"close"})
def _h_hurst(df, _name, _cache):
    # Hurst is a regime classifier — meaningful over the full series,
    # not a 20-bar trailing window. Compute once and broadcast.
    df["hurst_exponent"] = broadcast_scalar_over_series(_hurst, df["close"])
    return df

@_register("fractal_regime", requires={"close"})
def _h_frac_regime(df, _name, _cache):
    # fractal_regime returns a scalar string, not a Series.
    # Broadcast it as a constant for all bars.
    regime = _frac_regime(df["close"])
    df["fractal_regime"] = pd.Series(regime, index=df.index, dtype="object")
    return df


# --- Market regime (2) ---

@_register("market_regime", requires={"close", "high", "low", "volume"})
def _h_mkt_regime(df, _name, _cache):
    df["market_regime"] = _mkt_regime(df["close"], df["high"], df["low"], df["volume"])
    return df

@_register("day_type_classification", requires={"high", "low", "close"})
def _h_day_type(df, _name, _cache):
    df["day_type_classification"] = _day_type(df["high"], df["low"], df["close"])
    return df
