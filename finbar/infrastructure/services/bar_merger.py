"""Bar merger — combines primary and informative timeframes for multi-interval
backtesting.

When a strategy requires both intraday bars (e.g., 1h) and daily context
(e.g., trend indicators from 1d), the merger aligns daily indicator columns
to each primary bar's date and suffixes them with the informative interval.

Example:
  Primary (1h):   open, high, low, close, vwap, ib_high, ib_low
  Informative (1d): sma_50, sma_200, atr

  Merged (1h):    open, high, low, close, vwap, ib_high, ib_low,
                  sma_50_1d, sma_200_1d, atr_1d

This is used by multi-interval strategies like Auction Drive.
"""

from __future__ import annotations

import pandas as pd


def merge_timeframes(
    primary: pd.DataFrame,
    informative: pd.DataFrame,
    informative_interval: str = "1d",
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Merge informative timeframe columns into primary DataFrame.

    Aligns bars by date (YYYY-MM-DD). Each primary bar gets the
    informative bar values for its date, suffixed with the informative
    interval (e.g., sma_50 → sma_50_1d).

    Args:
        primary: DataFrame indexed by datetime (e.g., 1h bars).
        informative: DataFrame indexed by datetime (e.g., 1d bars).
        informative_interval: Suffix for informative columns (e.g., "1d").
        columns: Specific columns to merge. If None, merges all columns
            except OHLCV (open, high, low, close, volume, timestamp).

    Returns:
        Primary DataFrame with informative columns added with suffix.
    """
    result = primary.copy()

    if informative.empty:
        return result

    # Determine which columns to merge
    ohlcv = {"open", "high", "low", "close", "volume", "timestamp"}
    if columns is None:
        columns = [c for c in informative.columns if c not in ohlcv]

    if not columns:
        return result

    # Build date → indicator value lookup from informative DataFrame
    suffix = f"_{informative_interval}"
    info_by_date: dict[str, dict[str, float]] = {}

    for idx, row in informative.iterrows():
        date_str = _to_date_str(idx)
        for col in columns:
            val = row.get(col)
            if val is not None and pd.notna(val):
                info_by_date.setdefault(date_str, {})[f"{col}{suffix}"] = float(val)

    # Apply to each primary bar
    primary_dates = pd.to_datetime(primary.index).strftime("%Y-%m-%d")

    for merged_col in [f"{c}{suffix}" for c in columns]:
        result[merged_col] = primary_dates.map(
            lambda d: info_by_date.get(d, {}).get(merged_col)
        )

    return result


def _to_date_str(timestamp) -> str:
    """Convert a pandas Timestamp to YYYY-MM-DD string."""
    if hasattr(timestamp, "strftime"):
        return timestamp.strftime("%Y-%m-%d")
    return str(timestamp)[:10]
