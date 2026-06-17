"""No-lookahead as-of merge of derivatives data onto OHLCV bars.

A derivatives row timestamped T is available only at bar T + interval.
This reuses the proven offset logic from
``finbar_strategy_runtime.indicators.bar_merger.interval_offset`` to
guarantee consistency with the existing timeframe-merge no-lookahead
invariant.
"""

from __future__ import annotations

import pandas as pd
from finbar_strategy_runtime.indicators.bar_merger import interval_offset

from finbar.core.domain.entities.derivatives_metrics import (
    DERIVATIVES_FIELDS,
    DerivativesMetrics,
)

# Use the canonical field list from the entity (single source of truth).
_DERIVATIVES_COLUMNS: list[str] = list(DERIVATIVES_FIELDS)


def merge_derivatives_asof(
    ohlcv_df: pd.DataFrame,
    derivatives_rows: list[DerivativesMetrics],
    interval: str = "1h",
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Merge derivatives rows onto the OHLCV frame with no lookahead.

    A derivatives row timestamped T is available only at bar T + interval.
    This prevents lookahead bias: a bar at time T cannot see derivatives
    data published at T (which hasn't closed yet).

    Args:
        ohlcv_df: OHLCV DataFrame with a DatetimeIndex.
        derivatives_rows: ``list[DerivativesMetrics]`` from the repository.
        interval: Bar interval (e.g. "1h", "1d"). Determines the offset.
        columns: Which fields to merge. Defaults to all derivatives columns.

    Returns:
        A copy of ``ohlcv_df`` with derivatives columns added.
        Missing data produces NaN (Invariant #2 — column always exists).
    """
    target_cols = columns or _DERIVATIVES_COLUMNS
    result = ohlcv_df.copy()

    if not derivatives_rows:
        _add_empty_columns(result, target_cols)
        return result

    offset = interval_offset(interval)
    timestamps = pd.to_datetime([r.timestamp for r in derivatives_rows])
    availability = pd.DatetimeIndex(timestamps + offset)

    # Normalize timezone: make both indices tz-aware or both naive
    result_index = result.index
    if availability.tz is not None and result_index.tz is None:
        result_index = result_index.tz_localize(availability.tz)
    elif availability.tz is None and result_index.tz is not None:
        availability = availability.tz_localize(result_index.tz)
    elif (
        availability.tz is not None
        and result_index.tz is not None
        and availability.tz != result_index.tz
    ):
        # Both aware but in different zones: convert the availability index to
        # the result frame's timezone so the as-of reindex aligns instants.
        availability = availability.tz_convert(result_index.tz)

    avail_df = _build_availability_frame(
        derivatives_rows, availability, target_cols
    )

    aligned = avail_df.reindex(result_index, method="ffill")
    for col in target_cols:
        result[col] = aligned[col].values
    return result


def _add_empty_columns(df: pd.DataFrame, columns: list[str]) -> None:
    """Add all-NaN columns so handlers don't crash (Invariant #2)."""
    for col in columns:
        df[col] = pd.Series(dtype="float64", index=df.index)


def _build_availability_frame(
    rows: list[DerivativesMetrics],
    availability: pd.DatetimeIndex,
    columns: list[str],
) -> pd.DataFrame:
    """Build a DataFrame indexed by availability time."""
    data = {
        col: [_get_float(r, col) for r in rows] for col in columns
    }
    avail_df = pd.DataFrame(data, index=availability).sort_index()
    return avail_df[~avail_df.index.duplicated(keep="last")]


def _get_float(row: DerivativesMetrics, field: str) -> float | None:
    """Extract a float field from a DerivativesMetrics, returning None if NaN."""
    value = getattr(row, field, None)
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return f
