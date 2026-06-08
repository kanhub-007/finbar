"""Coil / Squeeze Detector — detects when value area is contracting (energy building).

When a market stays balanced (price inside a narrow value area, hugging POC)
for an extended period, it "coils" — building energy for an eventual explosive
breakout. This is a classic AMT/Wyckoff concept.

Detects:
  - is_coiled: bool — value area at multi-session low, price at POC
  - coil_intensity: float 0..100 — how extreme the contraction is

All functions are pure — no state, no I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def detect_coil(
    df: pd.DataFrame,
    lookback: int = 20,
    percentile: float = 20.0,
) -> pd.DataFrame:
    """Detect value area coil/squeeze conditions.

    A coil occurs when:
      1. Value area width is in the lowest ``percentile``% of recent sessions
      2. Price is inside the value area (close between VAL and VAH)
      3. Price is at or near POC (optional, adds confidence)

    Args:
        df: DataFrame with [close, vp_vah, vp_val, vp_poc] columns.
            Must also have value_area_width_pct (from auction_state).
        lookback: Number of sessions for the rolling percentile.
        percentile: Percentile threshold (default 20 = bottom 20%).

    Returns:
        DataFrame with added columns: is_coiled, coil_intensity.
    """
    result = df.copy()
    result["is_coiled"] = False
    result["coil_intensity"] = 0.0

    # Need VP + auction state columns
    required = {"vp_vah", "vp_val", "vp_poc"}
    if not required.issubset(result.columns):
        return result

    # Compute value_area_width_pct if not already present
    if "value_area_width_pct" not in result.columns:
        vah = result["vp_vah"]
        val = result["vp_val"]
        result["value_area_width_pct"] = np.where(
            vah > 0, (vah - val) / vah * 100.0, 0.0
        )

    # Compute inside_value if not already present
    if "inside_value" not in result.columns:
        result["inside_value"] = (
            result["close"] >= result["vp_val"]
        ) & (result["close"] <= result["vp_vah"])

    if "at_poc" not in result.columns:
        value_width = result["vp_vah"] - result["vp_val"]
        poc_distance = (result["close"] - result["vp_poc"]).abs()
        result["at_poc"] = poc_distance <= (value_width * 0.02)

    width = result["value_area_width_pct"]
    inside = result["inside_value"]
    at_poc = result["at_poc"]

    # Rolling percentile: for each bar, what percentile is current width
    # among the last lookback bars?
    rolling_bars = len(result)
    for i in range(lookback, rolling_bars):
        window = width.iloc[i - lookback : i]
        if window.isna().all():
            continue
        current_w = width.iloc[i]
        if np.isnan(current_w):
            continue

        # Percentile rank of current value in window
        count_below = (window < current_w).sum()
        pct_rank = count_below / lookback * 100.0

        # Coil: width in bottom X% AND (price inside value OR at POC)
        is_coiled = pct_rank < percentile and (bool(inside.iloc[i]) or bool(at_poc.iloc[i]))

        result.loc[result.index[i], "is_coiled"] = bool(is_coiled)

        # Intensity: how far below the threshold percentile
        threshold_width = np.percentile(window.dropna(), percentile)
        if threshold_width > 0 and is_coiled:
            intensity = (1.0 - current_w / threshold_width) * 100.0
            result.loc[result.index[i], "coil_intensity"] = float(
                min(max(intensity, 0.0), 100.0)
            )

    return result
