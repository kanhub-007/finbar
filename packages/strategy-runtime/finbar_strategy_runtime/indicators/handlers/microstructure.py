"""Microstructure handlers — spread, volatility, liquidity, order flow.

This module is imported by ``handlers/__init__.py`` which triggers
registration of all ``@_register`` decorators at import time.
"""

import pandas as pd

from finbar_strategy_runtime.indicators._handler_registry import _register


from finbar_strategy_runtime.domain.services.spread_proxies import (  # noqa: E402
    abdi_ranaldo_spread as _ar_calc,
    chung_zhang_spread as _cz_calc,
    corwin_schultz_spread as _cs_calc,
    effective_tick_spread as _et_calc,
    fong_holden_tran_spread as _fht_calc,
    lot_zero_return_spread as _lot_calc,
    roll_spread as _roll_calc,
)
from finbar_strategy_runtime.domain.services.volatility_estimators import (  # noqa: E402
    close_to_close_vol as _cc_vol,
    daily_return_kurtosis as _dr_kurt,
    daily_return_skewness as _dr_skew,
    garman_klass_vol as _gk_vol,
    gk_plus_overnight_vol as _gko_vol,
    meilijson_vol as _mj_vol,
    parkinson_vol as _pk_vol,
    rogers_satchell_vol as _rs_vol,
    yang_zhang_vol as _yz_vol,
)
from finbar_strategy_runtime.domain.services.liquidity_proxies import (  # noqa: E402
    amihud_illiq as _amihud,
    amivest_liquidity as _amivest,
    bao_pan_zhou_cost as _bpz,
    florackis_lambda as _flor,
    hasbrouck_daily_lambda as _hasb,
    liu_illiq as _liu,
)
from finbar_strategy_runtime.domain.services.order_flow_proxies import (  # noqa: E402
    bvc_buy_volume as _bvc_buy,
    bvc_ofi as _bvc_ofi,
    bvc_sell_volume as _bvc_sell,
    cumulative_signed_volume_ofi as _csv_ofi,
    return_volume_correlation as _rvc,
    signed_sqrt_volume_ofi as _ssq_ofi,
)
from finbar_strategy_runtime.domain.services.informed_trading_proxies import (  # noqa: E402
    daily_vpin as _vpin,
    spread_based_pin_proxy as _pin,
)
from finbar_strategy_runtime.domain.services.jump_risk_proxies import (  # noqa: E402
    cc_rs_jump_proxy as _cc_jump,
    extreme_return_flag as _ext_ret,
    jump_gap_proxy as _jump_gap,
    overnight_gap_proxy as _on_gap,
)
from finbar_strategy_runtime.domain.services.resiliency_proxies import (  # noqa: E402
    inverse_amihud_resiliency as _inv_amihud,
    resiliency_autocorr as _res_auto,
    resiliency_spread_to_impact as _res_si,
)
from finbar_strategy_runtime.domain.services.intraday_seasonality_proxies import (  # noqa: E402
    first_last_hour_vol_fraction as _flhvf,
    overnight_intraday_decomp as _oid,
    parametric_u_shape as _u_shape,
)
from finbar_strategy_runtime.domain.services.order_arrival_proxies import (  # noqa: E402
    volume_to_trade_count_proxy as _vtc,
)
from finbar_strategy_runtime.indicators.rolling_scalar_wrapper import (  # noqa: E402
    rolling_scalar_series,
)


# --- Spread proxies (7) ---

@_register("corwin_schultz_spread", requires={"open", "high", "low", "close"})
def _h_corwin_schultz(df, _name, _cache):
    df["corwin_schultz_spread"] = _cs_calc(df)
    return df

@_register("roll_spread", requires={"close"})
def _h_roll_spread(df, _name, _cache):
    df["roll_spread"] = rolling_scalar_series(_roll_calc, df["close"])
    return df

@_register("abdi_ranaldo_spread", requires={"open", "high", "low", "close"})
def _h_abdi_ranaldo(df, _name, _cache):
    df["abdi_ranaldo_spread"] = _ar_calc(df)
    return df

@_register("effective_tick_spread", requires={"close"})
def _h_effective_tick(df, _name, _cache):
    # Window must be >= effective_tick_spread's default lookback=60.
    # TODO: derive from inspect.signature(effective_tick_spread).parameters[
    #       "lookback"].default to avoid future drift (ADR-3).
    df["effective_tick_spread"] = rolling_scalar_series(
        _et_calc, df["close"], window=60
    )
    return df

@_register("fong_holden_tran_spread", requires={"open", "high", "low", "close"})
def _h_fht_spread(df, _name, _cache):
    df["fong_holden_tran_spread"] = _fht_calc(df)
    return df

@_register("chung_zhang_spread", requires={"open", "high", "low", "close"})
def _h_chung_zhang(df, _name, _cache):
    df["chung_zhang_spread"] = _cz_calc(df)
    return df

@_register("lot_zero_return_spread", requires={"close"})
def _h_lot_spread(df, _name, _cache):
    # Window must be >= lot_zero_return_spread's default lookback=60.
    # TODO: derive from inspect.signature (ADR-3).
    df["lot_zero_return_spread"] = rolling_scalar_series(
        _lot_calc, df["close"], window=60
    )
    return df


# --- Volatility estimators (9) ---

@_register("close_to_close_vol", requires={"close"})
def _h_cc_vol(df, _name, _cache):
    df["close_to_close_vol"] = _cc_vol(df["close"])
    return df

@_register("parkinson_vol", requires={"high", "low"})
def _h_parkinson(df, _name, _cache):
    df["parkinson_vol"] = _pk_vol(df["high"], df["low"])
    return df

@_register("garman_klass_vol", requires={"open", "high", "low", "close"})
def _h_gk_vol(df, _name, _cache):
    df["garman_klass_vol"] = _gk_vol(df)
    return df

@_register("rogers_satchell_vol", requires={"open", "high", "low", "close"})
def _h_rs_vol(df, _name, _cache):
    df["rogers_satchell_vol"] = _rs_vol(df)
    return df

@_register("yang_zhang_vol", requires={"open", "high", "low", "close"})
def _h_yz_vol(df, _name, _cache):
    df["yang_zhang_vol"] = _yz_vol(df)
    return df

@_register("gk_plus_overnight_vol", requires={"open", "high", "low", "close"})
def _h_gko_vol(df, _name, _cache):
    df["gk_plus_overnight_vol"] = _gko_vol(df)
    return df

@_register("meilijson_vol", requires={"open", "high", "low", "close"})
def _h_mj_vol(df, _name, _cache):
    df["meilijson_vol"] = _mj_vol(df)
    return df

@_register("daily_return_skewness", requires={"close"})
def _h_dr_skew(df, _name, _cache):
    df["daily_return_skewness"] = _dr_skew(df["close"])
    return df

@_register("daily_return_kurtosis", requires={"close"})
def _h_dr_kurt(df, _name, _cache):
    df["daily_return_kurtosis"] = _dr_kurt(df["close"])
    return df


# --- Liquidity / impact (6; turnover excluded) ---

@_register("amihud_illiq", requires={"close", "volume"})
def _h_amihud(df, _name, _cache):
    df["amihud_illiq"] = _amihud(df)
    return df

@_register("amivest_liquidity", requires={"close", "volume"})
def _h_amivest(df, _name, _cache):
    df["amivest_liquidity"] = _amivest(df)
    return df

@_register("florackis_lambda", requires={"close", "volume"})
def _h_florackis(df, _name, _cache):
    df["florackis_lambda"] = _flor(df)
    return df

@_register("hasbrouck_daily_lambda", requires={"close", "volume"})
def _h_hasbrouck(df, _name, _cache):
    df["hasbrouck_daily_lambda"] = _hasb(df)
    return df

@_register("liu_illiq", requires={"volume"})
def _h_liu(df, _name, _cache):
    # Window must be >= liu_illiq's default lookback=21.
    # TODO: derive from inspect.signature (ADR-3).
    df["liu_illiq"] = rolling_scalar_series(_liu, df["volume"], window=21)
    return df

@_register("bao_pan_zhou_cost", requires={"close"})
def _h_bpz(df, _name, _cache):
    df["bao_pan_zhou_cost"] = rolling_scalar_series(_bpz, df["close"])
    return df


# --- Order flow (6) ---

@_register("signed_sqrt_volume_ofi", requires={"close", "volume"})
def _h_ssq_ofi(df, _name, _cache):
    df["signed_sqrt_volume_ofi"] = _ssq_ofi(df)
    return df

@_register("cumulative_signed_volume_ofi", requires={"close", "volume"})
def _h_csv_ofi(df, _name, _cache):
    df["cumulative_signed_volume_ofi"] = _csv_ofi(df)
    return df

@_register("bvc_buy_volume", requires={"close", "volume"})
def _h_bvc_buy(df, _name, _cache):
    df["bvc_buy_volume"] = _bvc_buy(df)
    return df

@_register("bvc_sell_volume", requires={"close", "volume"})
def _h_bvc_sell(df, _name, _cache):
    df["bvc_sell_volume"] = _bvc_sell(df)
    return df

@_register("bvc_ofi", requires={"close", "volume"})
def _h_bvc_ofi(df, _name, _cache):
    df["bvc_ofi"] = _bvc_ofi(df)
    return df

@_register("return_volume_correlation", requires={"close", "volume"})
def _h_rvc(df, _name, _cache):
    df["return_volume_correlation"] = _rvc(df)
    return df


# --- Informed trading (2) ---

@_register("daily_vpin", requires={"close", "volume"})
def _h_daily_vpin(df, _name, _cache):
    df["daily_vpin"] = _vpin(df)
    return df

@_register("spread_based_pin_proxy", requires={"close", "volume"})
def _h_pin_proxy(df, _name, _cache):
    df["spread_based_pin_proxy"] = _pin(df)
    return df



# --- Jump risk (4) ---

@_register("jump_gap_proxy", requires={"open", "high", "low", "close"})
def _h_jump_gap(df, _name, _cache):
    df["jump_gap_proxy"] = _jump_gap(df)
    return df

@_register("extreme_return_flag", requires={"close"})
def _h_ext_ret(df, _name, _cache):
    df["extreme_return_flag"] = _ext_ret(df["close"])
    return df

@_register("cc_rs_jump_proxy", requires={"open", "high", "low", "close"})
def _h_cc_jump(df, _name, _cache):
    df["cc_rs_jump_proxy"] = _cc_jump(df)
    return df

@_register("overnight_gap_proxy", requires={"open", "high", "low", "close"})
def _h_on_gap(df, _name, _cache):
    df["overnight_gap_proxy"] = _on_gap(df)
    return df


# --- Resiliency (3) ---

@_register("resiliency_autocorr", requires={"close"})
def _h_res_auto(df, _name, _cache):
    # Calculator needs lookback(20) + lag(1) = 21 bars; window must cover both.
    # TODO: derive from inspect.signature (ADR-3).
    df["resiliency_autocorr"] = rolling_scalar_series(
        _res_auto, df["close"], window=21
    )
    return df

@_register("resiliency_spread_to_impact", requires={"close", "volume"})
def _h_res_si(df, _name, _cache):
    df["resiliency_spread_to_impact"] = _res_si(df)
    return df

@_register("inverse_amihud_resiliency", requires={"close", "volume"})
def _h_inv_amihud(df, _name, _cache):
    df["inverse_amihud_resiliency"] = _inv_amihud(df)
    return df


# --- Intraday seasonality (4) ---

@_register("overnight_return", requires={"open", "high", "low", "close"})
def _h_overnight_return(df, _name, _cache):
    overnight, _intraday = _oid(df)
    df["overnight_return"] = overnight
    return df

@_register("intraday_return", requires={"open", "high", "low", "close"})
def _h_intraday_return(df, _name, _cache):
    _overnight, intraday = _oid(df)
    df["intraday_return"] = intraday
    return df

@_register("parametric_u_shape", requires={"volume"})
def _h_u_shape(df, _name, _cache):
    df["parametric_u_shape"] = _u_shape(df["volume"])
    return df

@_register("first_last_hour_vol_fraction", requires={"close", "volume"})
def _h_flhvf(df, _name, _cache):
    df["first_last_hour_vol_fraction"] = _flhvf(df)
    return df


# --- Order arrival (2) ---

@_register("volume_to_trade_count_proxy", requires={"volume"})
def _h_vtc(df, _name, _cache):
    df["volume_to_trade_count_proxy"] = _vtc(df["volume"])
    return df


