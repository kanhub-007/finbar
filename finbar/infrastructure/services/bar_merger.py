"""Bar merger — combines primary and informative timeframes for backtests.

The merger uses no-lookahead as-of alignment. Informative bars become
available only after their interval has completed, so an intraday primary bar
on a given date cannot see that same date's daily close/indicators.
"""

from __future__ import annotations

import pandas as pd

from finbar.core.domain.services.indicator_value_mapper import to_numeric


def merge_timeframes(
    primary: pd.DataFrame,
    informative: pd.DataFrame,
    informative_interval: str = "1d",
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Merge informative timeframe columns into primary DataFrame.

    Informative values are aligned as-of their completion timestamp. For
    example, a daily bar stamped ``2024-01-02`` is considered available from
    ``2024-01-03 00:00:00`` when merged into intraday bars. This prevents
    same-day daily indicators from leaking into earlier intraday signals.

    Args:
        primary: DataFrame indexed by datetime (e.g., 1h bars).
        informative: DataFrame indexed by datetime (e.g., 1d bars).
        informative_interval: Suffix and availability interval (e.g., "1d").
        columns: Specific columns to merge. If None, merges all non-OHLCV
            columns from the informative frame.

    Returns:
        Primary DataFrame with suffixed informative columns added.
    """
    result = primary.copy()
    if informative.empty:
        return result

    selected = _selected_columns(informative, columns)
    if not selected:
        return result

    primary_index = pd.to_datetime(primary.index)
    info = _build_available_informative_frame(
        informative,
        selected,
        informative_interval,
    )
    if info.empty:
        return result

    aligned = info.reindex(primary_index, method="ffill")
    for column in aligned.columns:
        result[column] = aligned[column].to_numpy()
    return result


def _selected_columns(frame: pd.DataFrame, columns: list[str] | None) -> list[str]:
    """Return informative columns eligible for merging."""
    ohlcv = {"open", "high", "low", "close", "volume", "timestamp"}
    if columns is not None:
        return [column for column in columns if column in frame.columns]
    return [column for column in frame.columns if column not in ohlcv]


def _build_available_informative_frame(
    informative: pd.DataFrame,
    columns: list[str],
    informative_interval: str,
) -> pd.DataFrame:
    """Return numeric informative values indexed by availability timestamp."""
    suffix = f"_{informative_interval}"
    availability_index = _availability_index(informative.index, informative_interval)
    data: dict[str, pd.Series] = {}
    for column in columns:
        numeric = informative[column].map(to_numeric)
        data[f"{column}{suffix}"] = pd.Series(
            numeric.to_numpy(),
            index=availability_index,
        )
    frame = pd.DataFrame(data).sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    return frame.dropna(how="all")


def _availability_index(index, informative_interval: str) -> pd.DatetimeIndex:
    """Return timestamps when informative bars are safe to consume."""
    timestamps = pd.to_datetime(index)
    return pd.DatetimeIndex(timestamps + _interval_offset(informative_interval))


def _interval_offset(interval: str) -> pd.Timedelta:
    """Convert a Finbar interval string to a pandas Timedelta."""
    normalized = interval.lower().strip()
    offsets = {
        "5min": pd.Timedelta(minutes=5),
        "30min": pd.Timedelta(minutes=30),
        "1h": pd.Timedelta(hours=1),
        "1d": pd.Timedelta(days=1),
        "1w": pd.Timedelta(weeks=1),
    }
    return offsets.get(normalized, pd.Timedelta(0))
