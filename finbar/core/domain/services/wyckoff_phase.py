"""Wyckoff Phase Classifier — identifies market phase from AMT + Wyckoff signals.

Combines Volume Profile metrics (POC migration, value area width, profile shape)
with balance status to classify the current Wyckoff phase:

  ACCUMULATION  — POC stable, VA contracting, volume declining, normal/b-shape
  MARKUP        — POC rising, VA expanding, volume increasing, p-shapes
  DISTRIBUTION  — POC flat/waffling, VA wide, high volume, d-shapes
  MARKDOWN      — POC falling, VA expanding, volume increasing
  NEUTRAL       — No clear phase, choppy conditions

All functions are pure — no state, no I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_poc_slope(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """Compute POC migration as percentage change over N sessions.

    Groups by session, takes the last POC value per session, computes
    rolling % change.

    Args:
        df: DataFrame with vp_poc column.
        window: Number of sessions for slope (default 5).

    Returns:
        Series: POC % change over ``window`` sessions.
    """
    if "vp_poc" not in df.columns:
        return pd.Series(0.0, index=df.index)

    date_series = pd.Series(
        pd.to_datetime(df.index).strftime("%Y-%m-%d"), index=df.index
    )
    ordered_dates = sorted(date_series.unique())

    session_pocs: dict[str, float] = {}
    for date, idx in date_series.groupby(date_series).groups.items():
        session_pocs[date] = float(df["vp_poc"].loc[idx].iloc[-1])

    slope = pd.Series(0.0, index=df.index)

    for i, date in enumerate(ordered_dates):
        if i < window:
            continue
        old_date = ordered_dates[i - window]
        old_poc = session_pocs.get(old_date, 0)
        new_poc = session_pocs.get(date, 0)
        if old_poc > 0:
            pct_change = (new_poc - old_poc) / old_poc * 100.0
            idx = date_series[date_series == date].index
            slope.loc[idx] = pct_change

    return slope


def classify_wyckoff_phase(
    df: pd.DataFrame,
    slope_window: int = 20,
) -> pd.DataFrame:
    """Classify each bar's Wyckoff phase from AMT indicators.

    Requires these columns to already exist:
      - vp_poc, vp_vah, vp_val (Volume Profile)
      - balance_status (auction state)
      - profile_shape (profile classifier)
      - rvol (relative volume)
      - value_area_width_pct (auction state)

    Args:
        df: Enriched DataFrame with VP, auction state, profile shape.
        slope_window: Number of sessions for POC slope calculation.
            Controls sensitivity: lower = faster phase detection,
            higher = smoother, fewer whipsaws. Default 20 per Wyckoff
            literature (multi-week phase changes).

    Adds columns:
      - poc_slope_5: float — POC % change over 5 sessions (fast)
      - poc_slope_20: float — POC % change over 20 sessions (slow)
      - wyckoff_phase: str — ACCUMULATION | MARKUP | DISTRIBUTION | MARKDOWN | NEUTRAL
    """
    result = df.copy()

    # Always compute both fast and slow slopes as standalone indicators
    result["poc_slope_5"] = compute_poc_slope(result, window=5)
    result["poc_slope_20"] = compute_poc_slope(result, window=20)

    # Use the parameterized slope for classification logic
    slope_col = f"poc_slope_{slope_window}"
    if slope_col not in result.columns:
        result[slope_col] = compute_poc_slope(result, window=slope_window)

    result["wyckoff_phase"] = "NEUTRAL"

    # Need base columns
    if "vp_poc" not in result.columns or "balance_status" not in result.columns:
        return result

    # Get column references
    slope = result[slope_col]
    width = result.get("value_area_width_pct", pd.Series(0.0, index=result.index))
    balance = result.get("balance_status", pd.Series("BALANCED", index=result.index))
    rvol = result.get("rvol", pd.Series(1.0, index=result.index))
    shape = result.get("profile_shape", pd.Series("NEUTRAL", index=result.index))

    # Width direction: expanding or contracting
    width_direction = width - width.shift(5)

    # --- MARKUP: POC rising, imbalance up ---
    # Plan: poc_slope > 0.5%, IMBALANCED_UP
    markup = (
        (slope > 0.5)
        & (balance.isin(["IMBALANCED_UP"]))
    )

    # --- MARKDOWN: POC falling, imbalance down ---
    # Plan: poc_slope < -0.5%, IMBALANCED_DOWN
    markdown = (
        (slope < -0.5)
        & (balance.isin(["IMBALANCED_DOWN"]))
    )

    # --- ACCUMULATION: POC flat, VA contracting, balance, declining vol, normal/b-shape ---
    # Plan: |slope| < 0.2%, VA contracting, BALANCED, normal/b-shape, rvol < 1.0
    accumulation = (
        (slope.abs() < 0.2)
        & (width_direction < 0)
        & (balance == "BALANCED")
        & (shape.isin(["NORMAL", "B_SHAPE"]))
        & (rvol < 1.0)
    )

    # --- DISTRIBUTION: POC flat, VA wide+expanding, high vol, d-shapes ---
    # Plan: VA wide + expanding, d-shapes, high volume
    distribution = (
        (slope.abs() < 1.0)
        & (width_direction > 0)
        & (width > width.rolling(20, min_periods=5).mean())
        & (rvol > 1.0)
        & (shape.isin(["D_SHAPE", "NORMAL"]))
    )

    # Apply phases in priority order (MARKUP/MARKDOWN override others)
    result.loc[markup, "wyckoff_phase"] = "MARKUP"
    result.loc[markdown, "wyckoff_phase"] = "MARKDOWN"
    result.loc[accumulation, "wyckoff_phase"] = "ACCUMULATION"
    result.loc[distribution, "wyckoff_phase"] = "DISTRIBUTION"

    return result
