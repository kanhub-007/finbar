"""Composite Volume Profile — true multi-session stacked volume profiles.

Unlike VP rolling composites (which take median of session POCs), this
stacks ALL bars from N sessions into one big profile. Preserves volume
weight — high-volume sessions count more than low-volume ones.

This is what the AMT literature calls "composite profiles" — the primary
tool for identifying multi-session value areas.

All functions are pure — no state, no I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from finbar.core.domain.services.volume_profile import (
    compute_session_volume_profile,
)


def compute_composite_vp(
    df: pd.DataFrame,
    window: int = 5,
    num_buckets: int = 100,
) -> pd.DataFrame:
    """Compute true composite Volume Profile over N sessions.

    Stacks all bars from the last ``window`` sessions into one volume
    profile, then extracts POC/VAH/VAL from the combined distribution.

    Unlike ``compute_rolling_vp`` (which takes the median of per-session
    POCs), this aggregates raw volume across sessions — high-volume
    sessions naturally carry more weight.

    Args:
        df: DataFrame with columns [high, low, close, volume]
            and a datetime index.
        window: Number of sessions to stack (default 5).
        num_buckets: Price buckets per profile.

    Returns:
        DataFrame with columns: cvp_poc_{window}d, cvp_vah_{window}d,
        cvp_val_{window}d.
    """
    result = df.copy()

    poc_col = f"cvp_poc_{window}d"
    vah_col = f"cvp_vah_{window}d"
    val_col = f"cvp_val_{window}d"

    result[poc_col] = np.nan
    result[vah_col] = np.nan
    result[val_col] = np.nan

    # Group by calendar date
    date_series = pd.Series(
        pd.to_datetime(result.index).strftime("%Y-%m-%d"), index=result.index
    )

    # Get ordered list of session dates
    ordered_dates = sorted(date_series.unique())

    if len(ordered_dates) < window:
        return result

    for i in range(window - 1, len(ordered_dates)):
        # Collect all bars from the last ``window`` sessions
        w_dates = ordered_dates[i - window + 1 : i + 1]
        combined_bars = df.loc[date_series.isin(w_dates)]

        if combined_bars.empty:
            continue

        profile = compute_session_volume_profile(
            combined_bars, num_buckets=num_buckets
        )

        # Broadcast to current session's bars
        current_date = ordered_dates[i]
        idx = date_series[date_series == current_date].index
        result.loc[idx, poc_col] = profile.poc
        result.loc[idx, vah_col] = profile.vah
        result.loc[idx, val_col] = profile.val

    return result
