"""VWAP session bands handlers.

This module is imported by ``handlers/__init__.py`` which triggers
registration of all ``@_register`` decorators at import time.
"""

import pandas as pd

from finbar_strategy_runtime.domain.services.vwap_bands import compute_vwap_session_bands
from finbar_strategy_runtime.indicators._handler_registry import _register


@_register("vwap_upper_1")
def _vwap_upper_1(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_vwap_bands(df, cache)


@_register("vwap_lower_1")
def _vwap_lower_1(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_vwap_bands(df, cache)


@_register("vwap_upper_2")
def _vwap_upper_2(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_vwap_bands(df, cache)


@_register("vwap_lower_2")
def _vwap_lower_2(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_vwap_bands(df, cache)


def _compute_vwap_bands(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    """Compute session-scoped VWAP and its SD bands (cached across calls)."""
    if _VWAP_BANDS_CACHE_KEY in cache:
        return df
    result = compute_vwap_session_bands(df)
    cache[_VWAP_BANDS_CACHE_KEY] = True
    # Copy columns back to original df
    for col in (
        "vwap_session",
        "vwap_upper_1",
        "vwap_lower_1",
        "vwap_upper_2",
        "vwap_lower_2",
    ):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Proxy Volume Profile — POC/VAH/VAL (Auction Market Theory)
# ---------------------------------------------------------------------------

_VP_CACHE_KEY = "__volume_profile_done"
