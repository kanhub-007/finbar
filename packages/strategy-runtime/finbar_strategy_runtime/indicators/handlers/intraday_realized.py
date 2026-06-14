"""Realized-volatility and intraday volume-curve handlers.

This module is imported by ``handlers/__init__.py`` which triggers
registration of all ``@_register`` decorators at import time.
"""

import pandas as pd

from finbar_strategy_runtime.indicators._handler_registry import _register


from finbar_strategy_runtime.domain.services.realized_volatility_estimators import (  # noqa: E402
    bipower_variation as _bpv,
    lee_mykland_jump as _lm_jump,
    realized_kurtosis as _r_kurt,
    realized_skewness as _r_skew,
    realized_volatility as _r_vol,
)
from finbar_strategy_runtime.domain.services.intraday_seasonality_proxies import (  # noqa: E402
    empirical_volume_curve as _emp_vc,
    intraday_volume_curve as _intra_vc,
)


@_register("realized_vol_5m", requires={"close"})
def _h_rv_5m(df, _name, _cache):
    df["realized_vol_5m"] = _r_vol(df["close"], window=78)
    return df

@_register("realized_vol_15m", requires={"close"})
def _h_rv_15m(df, _name, _cache):
    df["realized_vol_15m"] = _r_vol(df["close"], window=26)
    return df

@_register("realized_vol_1h", requires={"close"})
def _h_rv_1h(df, _name, _cache):
    df["realized_vol_1h"] = _r_vol(df["close"], window=7)
    return df

@_register("bipower_variation", requires={"close"})
def _h_bpv(df, _name, _cache):
    df["bipower_variation"] = _bpv(df["close"], window=78)
    return df

@_register("realized_skewness", requires={"close"})
def _h_rskew(df, _name, _cache):
    df["realized_skewness"] = _r_skew(df["close"], window=78)
    return df

@_register("realized_kurtosis", requires={"close"})
def _h_rkurt(df, _name, _cache):
    df["realized_kurtosis"] = _r_kurt(df["close"], window=78)
    return df

@_register("lee_mykland_jump", requires={"close"})
def _h_lm_jump(df, _name, _cache):
    df["lee_mykland_jump"] = _lm_jump(df["close"], window=78)
    return df

@_register("intraday_volume_curve", requires={"volume"})
def _h_intra_vc(df, _name, _cache):
    df["intraday_volume_curve"] = _intra_vc(df)
    return df

@_register("empirical_volume_curve", requires={"volume"})
def _h_emp_vc(df, _name, _cache):
    df["empirical_volume_curve"] = _emp_vc(df)
    return df
