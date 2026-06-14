"""Market-profile (TPO) and Auction-Market-Theory signal handlers.

This module is imported by ``handlers/__init__.py`` which triggers
registration of all ``@_register`` decorators at import time.
"""

import pandas as pd

from finbar_strategy_runtime.domain.services.market_profile import (
    compute_all_session_market_profiles,
)
from finbar_strategy_runtime.domain.services.auction_state import (
    classify_auction_state,
)
from finbar_strategy_runtime.domain.services.amt_signals import (
    compute_amt_signals,
)
from finbar_strategy_runtime.indicators._handler_registry import _register

_MP_CACHE_KEY = "__market_profile_done"


@_register("mp_poc")
def _mp_poc(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_market_profile(df, cache)


@_register("mp_vah")
def _mp_vah(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_market_profile(df, cache)


@_register("mp_val")
def _mp_val(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_market_profile(df, cache)


def _compute_market_profile(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    """Compute session Market Profile (TPO-based POC/VAH/VAL), cached."""
    if _MP_CACHE_KEY in cache:
        return df
    result = compute_all_session_market_profiles(df)
    cache[_MP_CACHE_KEY] = True
    for col in ("mp_poc", "mp_vah", "mp_val"):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Auction State Classifiers (Auction Market Theory)
# ---------------------------------------------------------------------------

_AUCTION_STATE_CACHE_KEY = "__auction_state_done"


@_register("inside_value", requires={"vp_vah", "vp_val"})
def _inside_value(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("above_value", requires={"vp_vah"})
def _above_value(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("below_value", requires={"vp_val"})
def _below_value(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("at_poc", requires={"vp_poc", "vp_vah", "vp_val"})
def _at_poc(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("near_vah", requires={"vp_vah", "vp_val"})
def _near_vah(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("near_val", requires={"vp_vah", "vp_val"})
def _near_val(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("distance_to_vah_pct", requires={"vp_vah"})
def _distance_to_vah_pct(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("distance_to_val_pct", requires={"vp_val"})
def _distance_to_val_pct(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("value_area_width_pct", requires={"vp_vah", "vp_val"})
def _value_area_width_pct(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("balance_status", requires={"vp_vah", "vp_val"})
def _balance_status(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


def _compute_auction_state(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    """Compute all auction state classifiers (cached across calls)."""
    if _AUCTION_STATE_CACHE_KEY in cache:
        return df
    result = classify_auction_state(df)
    cache[_AUCTION_STATE_CACHE_KEY] = True
    auction_cols = [
        "inside_value",
        "above_value",
        "below_value",
        "at_poc",
        "near_vah",
        "near_val",
        "distance_to_vah_pct",
        "distance_to_val_pct",
        "value_area_width_pct",
        "balance_status",
    ]
    for col in auction_cols:
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# AMT Rule Signals (Auction Market Theory)
# ---------------------------------------------------------------------------

_AMT_SIGNALS_CACHE_KEY = "__amt_signals_done"


@_register("acceptance_into_value", requires={"vp_vah", "vp_val"})
def _acceptance_into_value(
    df: pd.DataFrame, _name: str, cache: dict
) -> pd.DataFrame:
    return _compute_amt_signals(df, cache)


@_register("rejection_from_edge", requires={"vp_vah", "vp_val"})
def _rejection_from_edge(
    df: pd.DataFrame, _name: str, cache: dict
) -> pd.DataFrame:
    return _compute_amt_signals(df, cache)


@_register("acceptance_outside_value", requires={"vp_vah", "vp_val"})
def _acceptance_outside_value(
    df: pd.DataFrame, _name: str, cache: dict
) -> pd.DataFrame:
    return _compute_amt_signals(df, cache)


@_register("poc_rejection", requires={"vp_poc", "atr"})
def _poc_rejection(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_amt_signals(df, cache)


@_register("edge_volume_building", requires={"vp_vah", "vp_val", "rvol"})
def _edge_volume_building(
    df: pd.DataFrame, _name: str, cache: dict
) -> pd.DataFrame:
    return _compute_amt_signals(df, cache)


@_register("value_area_migration", requires={"vp_poc"})
def _value_area_migration(
    df: pd.DataFrame, _name: str, cache: dict
) -> pd.DataFrame:
    return _compute_amt_signals(df, cache)


def _compute_amt_signals(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    """Compute all AMT rule signals (cached across calls).

    Ensures auction state columns are computed first as dependencies.
    """
    if _AMT_SIGNALS_CACHE_KEY in cache:
        return df

    # Ensure auction state dependencies are satisfied
    if _AUCTION_STATE_CACHE_KEY not in cache:
        df = _compute_auction_state(df, cache)

    result = compute_amt_signals(df)
    cache[_AMT_SIGNALS_CACHE_KEY] = True

    amt_cols = [
        "acceptance_into_value",
        "rejection_from_edge",
        "acceptance_outside_value",
        "poc_rejection",
        "edge_volume_building",
        "value_area_migration",
    ]
    for col in amt_cols:
        if col in result.columns:
            df[col] = result[col]
    return df
