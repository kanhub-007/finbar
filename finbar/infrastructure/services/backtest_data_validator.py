"""Backtest data validation helpers.

These functions validate the minimum OHLCV invariants needed before the
backtest loop starts. They return a human-readable error string instead of
raising so callers can surface structured backtest errors consistently.
"""

from __future__ import annotations

import pandas as pd

_REQUIRED_PRICE_COLUMNS = ("open", "high", "low", "close")


def validate_backtest_frame(frame: pd.DataFrame) -> str | None:
    """Return an error message when a backtest frame is not executable.

    Args:
        frame: OHLCV/indicator frame passed to the backtest engine.

    Returns:
        None when valid, otherwise a message describing the first validation
        failure class and example row.
    """
    missing_columns = [
        column for column in _REQUIRED_PRICE_COLUMNS if column not in frame.columns
    ]
    if missing_columns:
        return "Missing required OHLC columns: " + ", ".join(missing_columns)

    index_error = _validate_index(frame)
    if index_error is not None:
        return index_error

    numeric = _numeric_prices(frame)
    numeric_error = _validate_numeric_prices(numeric)
    if numeric_error is not None:
        return numeric_error

    return _validate_price_consistency(numeric)


def _validate_index(frame: pd.DataFrame) -> str | None:
    """Validate index ordering and duplicates when an index is meaningful."""
    if frame.index.has_duplicates:
        duplicate = frame.index[frame.index.duplicated()][0]
        return f"Duplicate bar timestamp/index: {duplicate}"
    if not frame.index.is_monotonic_increasing:
        return "Backtest bars must be sorted by timestamp/index"
    return None


def _numeric_prices(frame: pd.DataFrame) -> pd.DataFrame:
    """Return OHLC columns coerced to numeric values."""
    return _to_numeric_subset(frame, list(_REQUIRED_PRICE_COLUMNS))


def _validate_numeric_prices(prices: pd.DataFrame) -> str | None:
    """Validate price columns are present, numeric, and positive."""
    missing_mask = prices.isna().any(axis=1)
    if missing_mask.any():
        row = _row_label(prices, missing_mask)
        return f"OHLC values must be numeric and non-missing at {row}"

    non_positive_mask = (prices <= 0).any(axis=1)
    if non_positive_mask.any():
        row = _row_label(prices, non_positive_mask)
        return f"OHLC values must be positive at {row}"
    return None


def _validate_price_consistency(prices: pd.DataFrame) -> str | None:
    """Validate high/low enclose open and close for every bar."""
    high_low_mask = prices["high"] < prices["low"]
    if high_low_mask.any():
        row = _row_label(prices, high_low_mask)
        return f"Invalid OHLC bar: high is below low at {row}"

    high_encloses_mask = (prices["high"] < prices["open"]) | (
        prices["high"] < prices["close"]
    )
    if high_encloses_mask.any():
        row = _row_label(prices, high_encloses_mask)
        return f"Invalid OHLC bar: high is below open/close at {row}"

    low_encloses_mask = (prices["low"] > prices["open"]) | (
        prices["low"] > prices["close"]
    )
    if low_encloses_mask.any():
        row = _row_label(prices, low_encloses_mask)
        return f"Invalid OHLC bar: low is above open/close at {row}"
    return None


def _row_label(frame: pd.DataFrame, mask: pd.Series) -> str:
    """Return the first row label matching a boolean mask."""
    return str(frame.index[mask][0])


def validate_required_data(
    frame: pd.DataFrame,
    required_columns: list[str],
) -> dict:
    """Check that strategy-required indicator and feature columns are valid
    after each indicator's natural warmup.

    Delegates to the shared ``RequiredDataValidator`` in the strategy
    runtime package so finbar and finbot use the same implementation.

    Returns:
        Dict with warmup_bars, first_tradable, and per-column diagnostics.
    """
    from finbar_strategy_runtime.indicators.required_data_validator import (
        RequiredDataValidator,
    )

    return RequiredDataValidator().validate(frame, required_columns)


def _to_numeric_subset(
    frame: pd.DataFrame, columns: list[str]
) -> pd.DataFrame:
    """Return a numeric-only subset, skipping coercion for float columns.

    Most columns in an enriched frame are already float64 (from pandas_ta).
    Calling pd.to_numeric on them is a no-op copy that wastes time on large
    frames.
    """
    numeric_cols = set(frame.select_dtypes(include=["number"]).columns)
    parts: dict[str, pd.Series] = {}
    for col in columns:
        if col in numeric_cols:
            parts[col] = frame[col].astype(float)
        else:
            parts[col] = pd.to_numeric(frame[col], errors="coerce")
    return pd.DataFrame(parts, index=frame.index)
