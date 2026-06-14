"""Volume-profile handlers — session VP, rolling VP, composite VP.

This module is imported by ``handlers/__init__.py`` which triggers
registration of all ``@_register`` decorators at import time.
"""

import pandas as pd

from finbar_strategy_runtime.domain.services.volume_profile import (
    compute_all_session_volume_profiles,
    compute_rolling_vp,
    compute_rolling_window_vp,
)
from finbar_strategy_runtime.domain.services.composite_vp import (
    compute_composite_vp,
)
from finbar_strategy_runtime.indicators._handler_registry import _register

_VP_CACHE_KEY = "__volume_profile_done"


@_register("vp_poc")
def _vp_poc(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_volume_profile(df, cache)


@_register("vp_vah")
def _vp_vah(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_volume_profile(df, cache)


@_register("vp_val")
def _vp_val(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_volume_profile(df, cache)


def _compute_volume_profile(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    """Compute session Volume Profile (POC/VAH/VAL), cached across calls."""
    if _VP_CACHE_KEY in cache:
        return df
    result = compute_all_session_volume_profiles(df)
    cache[_VP_CACHE_KEY] = True
    for col in ("vp_poc", "vp_vah", "vp_val"):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Rolling / Composite Volume Profile
# ---------------------------------------------------------------------------

_ROLLING_VP_CACHE_KEY = "__rolling_vp_done"

# Parameterized rolling VP prefixes for dynamic resolution
_ROLLING_VP_PREFIXES = {"vp_poc_", "vp_vah_", "vp_val_"}
# Rolling-window VP prefixes (bar-based, for crypto/24-7 markets)
_RVP_PREFIXES = {"rvp_poc_", "rvp_vah_", "rvp_val_"}
_CVP_PREFIXES = {"cvp_poc_", "cvp_vah_", "cvp_val_"}


@_register("vp_poc_5d", requires={"vp_poc", "vp_vah", "vp_val"})
def _vp_poc_5d(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_vp(df, cache, 5)
    return df


@_register("vp_vah_5d", requires={"vp_poc", "vp_vah", "vp_val"})
def _vp_vah_5d(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_vp(df, cache, 5)
    return df


@_register("vp_val_5d", requires={"vp_poc", "vp_vah", "vp_val"})
def _vp_val_5d(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_vp(df, cache, 5)
    return df


@_register("vp_poc_20d", requires={"vp_poc", "vp_vah", "vp_val"})
def _vp_poc_20d(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_vp(df, cache, 20)
    return df


@_register("vp_vah_20d", requires={"vp_poc", "vp_vah", "vp_val"})
def _vp_vah_20d(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_vp(df, cache, 20)
    return df


@_register("vp_val_20d", requires={"vp_poc", "vp_vah", "vp_val"})
def _vp_val_20d(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_vp(df, cache, 20)
    return df


def _compute_rolling_vp(df: pd.DataFrame, cache: dict, window: int) -> pd.DataFrame:
    """Compute rolling VP composites for a specific window (cached)."""
    cache_key = f"{_ROLLING_VP_CACHE_KEY}_{window}"
    if cache_key in cache:
        return df
    result = compute_rolling_vp(df, window=window)
    cache[cache_key] = True
    for col in (f"vp_poc_{window}d", f"vp_vah_{window}d", f"vp_val_{window}d"):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Rolling-window Volume Profile — bar-based windows (crypto / 24-7 markets)
# ---------------------------------------------------------------------------

_RVP_CACHE_KEY = "__rolling_window_vp_done"


@_register("rvp_poc_48")
def _rvp_poc_48(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 48)
    return df


@_register("rvp_vah_48")
def _rvp_vah_48(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 48)
    return df


@_register("rvp_val_48")
def _rvp_val_48(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 48)
    return df


@_register("rvp_poc_96")
def _rvp_poc_96(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 96)
    return df


@_register("rvp_vah_96")
def _rvp_vah_96(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 96)
    return df


@_register("rvp_val_96")
def _rvp_val_96(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 96)
    return df


@_register("rvp_poc_336")
def _rvp_poc_336(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 336)
    return df


@_register("rvp_vah_336")
def _rvp_vah_336(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 336)
    return df


@_register("rvp_val_336")
def _rvp_val_336(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 336)
    return df


def _compute_rolling_window_vp(
    df: pd.DataFrame, cache: dict, window_bars: int
) -> pd.DataFrame:
    """Compute rolling-window VP for a specific bar count (cached)."""
    cache_key = f"{_RVP_CACHE_KEY}_{window_bars}"
    if cache_key in cache:
        return df
    result = compute_rolling_window_vp(df, window_bars=window_bars)
    cache[cache_key] = True
    for col in (
        f"rvp_poc_{window_bars}",
        f"rvp_vah_{window_bars}",
        f"rvp_val_{window_bars}",
    ):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Composite Volume Profile
# ---------------------------------------------------------------------------

_CVP_CACHE_KEY = "__composite_vp_done"


@_register("cvp_poc_5d")
def _cvp_poc_5d(df, _name, cache):
    _compute_composite_vp(df, cache, 5)
    return df


@_register("cvp_vah_5d")
def _cvp_vah_5d(df, _name, cache):
    _compute_composite_vp(df, cache, 5)
    return df


@_register("cvp_val_5d")
def _cvp_val_5d(df, _name, cache):
    _compute_composite_vp(df, cache, 5)
    return df


@_register("cvp_poc_10d")
def _cvp_poc_10d(df, _name, cache):
    _compute_composite_vp(df, cache, 10)
    return df


@_register("cvp_vah_10d")
def _cvp_vah_10d(df, _name, cache):
    _compute_composite_vp(df, cache, 10)
    return df


@_register("cvp_val_10d")
def _cvp_val_10d(df, _name, cache):
    _compute_composite_vp(df, cache, 10)
    return df


@_register("cvp_poc_20d")
def _cvp_poc_20d(df, _name, cache):
    _compute_composite_vp(df, cache, 20)
    return df


@_register("cvp_vah_20d")
def _cvp_vah_20d(df, _name, cache):
    _compute_composite_vp(df, cache, 20)
    return df


@_register("cvp_val_20d")
def _cvp_val_20d(df, _name, cache):
    _compute_composite_vp(df, cache, 20)
    return df


def _compute_composite_vp(df, cache, window):
    cache_key = f"{_CVP_CACHE_KEY}_{window}"
    if cache_key in cache:
        return df
    result = compute_composite_vp(df, window=window)
    cache[cache_key] = True
    for col in (f"cvp_poc_{window}d", f"cvp_vah_{window}d", f"cvp_val_{window}d"):
        if col in result.columns:
            df[col] = result[col]
    return df
