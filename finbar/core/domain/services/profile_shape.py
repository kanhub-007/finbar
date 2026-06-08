"""Profile Shape Classifier — classifies daily profile shapes from Market Profile literature.

Given a session's OHLCV bars, computes the Volume Profile histogram and
classifies the shape into one of five categories:

  NORMAL   — Balanced, POC centered, single distribution
  B_SHAPE  — Bimodal, POC at joint. Reversal day (early move rejected)
  P_SHAPE  — Trend up. POC near the low range. Price opened low, trended up.
  D_SHAPE  — Trend down. POC near the high range. Price opened high, trended down.
  NEUTRAL  — Low volume, no clear distribution shape.

All functions are pure — no state, no I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from finbar.core.domain.services.volume_profile import (
    compute_session_volume_profile,
)


# ---------------------------------------------------------------------------
# Single-session shape classification from profile data
# ---------------------------------------------------------------------------


def classify_profile_shape_from_array(
    volume_profile: np.ndarray,
    total_volume: float,
    avg_session_volume: float,
) -> str:
    """Classify shape from a pre-computed volume distribution.

    Args:
        volume_profile: 1-D array of volume per price bucket.
        total_volume: Total volume for this session.
        avg_session_volume: Average volume across recent sessions.

    Returns:
        One of 'NORMAL', 'B_SHAPE', 'P_SHAPE', 'D_SHAPE', 'NEUTRAL'.
    """
    if total_volume <= 0 or len(volume_profile) < 10:
        return "NEUTRAL"

    # Low volume → neutral
    if avg_session_volume > 0 and total_volume < avg_session_volume * 0.5:
        return "NEUTRAL"

    num_buckets = len(volume_profile)
    poc_idx = int(np.argmax(volume_profile))
    poc_volume = volume_profile[poc_idx]
    poc_position = poc_idx / (num_buckets - 1)  # 0.0 = bottom, 1.0 = top

    # Check for bimodality: second peak > 50% of POC, far from POC
    min_distance = int(num_buckets * 0.15)
    for i in range(num_buckets):
        if i == poc_idx or volume_profile[i] <= 0:
            continue
        if (
            abs(i - poc_idx) >= min_distance
            and volume_profile[i] > poc_volume * 0.5
        ):
            return "B_SHAPE"

    # Unimodal: check POC position
    if poc_position < 0.3:
        return "P_SHAPE"
    elif poc_position > 0.7:
        return "D_SHAPE"
    else:
        return "NORMAL"


# ---------------------------------------------------------------------------
# DataFrame-level classification (per session)
# ---------------------------------------------------------------------------


def classify_all_profile_shapes(
    df: pd.DataFrame,
    avg_volume_lookback: int = 20,
    num_buckets: int = 100,
) -> pd.DataFrame:
    """Classify profile shape for each session in the DataFrame.

    Computes a Volume Profile per session internally (does not depend on
    pre-computed VP columns).

    Args:
        df: DataFrame with columns [high, low, close, volume]
            and a datetime index.
        avg_volume_lookback: Sessions for average volume baseline.
        num_buckets: Price buckets per profile.

    Returns:
        DataFrame with added column: profile_shape.
    """
    result = df.copy()
    result["profile_shape"] = "NEUTRAL"

    date_series = pd.Series(
        pd.to_datetime(result.index).strftime("%Y-%m-%d"), index=result.index
    )
    ordered_dates = sorted(date_series.unique())

    if len(ordered_dates) < 5:
        return result

    # Pre-compute volume per session
    session_volumes: dict[str, float] = {}
    for date, idx in date_series.groupby(date_series).groups.items():
        session_volumes[date] = float(df["volume"].loc[idx].sum())

    for i, date in enumerate(ordered_dates):
        idx = date_series[date_series == date].index
        session = df.loc[idx]

        # Average volume over recent sessions
        lookback_start = max(0, i - avg_volume_lookback)
        recent = [session_volumes[d] for d in ordered_dates[lookback_start:i]]
        avg_vol = float(np.mean(recent)) if recent else 0.0

        # Compute profile and classify
        profile = compute_session_volume_profile(session, num_buckets=num_buckets)
        if profile.total_volume <= 0 or not profile.profile:
            continue

        # Convert profile dict to sorted array by price
        sorted_prices = sorted(profile.profile.keys())
        vp_array = np.array([profile.profile[p] for p in sorted_prices])

        shape = classify_profile_shape_from_array(
            vp_array,
            profile.total_volume,
            avg_vol,
        )
        result.loc[idx, "profile_shape"] = shape

    return result
