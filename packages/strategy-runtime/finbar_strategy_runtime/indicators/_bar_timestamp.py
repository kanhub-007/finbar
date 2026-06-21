"""Shared bar-timestamp parsing helper.

Production bars arrive as int Unix seconds (Finbot/Hyperliquid), but
inputs may also be ISO-8601 strings, Python datetimes, or large-numeric
milliseconds. Parsing is centralised here so the batch converter and the
streaming windowed fallback agree on timestamp semantics.

A silent unit misparse (int seconds read as nanoseconds) would corrupt
session grouping and break live parity, so large numeric values are
auto-detected as milliseconds.
"""

from __future__ import annotations

import pandas as pd

# Numeric values at or above this threshold are interpreted as Unix
# milliseconds rather than seconds. Modern seconds timestamps are ~1.7e9;
# millisecond timestamps are ~1.7e12. 1e11 seconds is year ~5138, so no
# realistic seconds value reaches it, and no modern millisecond value
# falls below it.
MS_THRESHOLD = 1e11


def parse_bar_timestamps(values) -> pd.DatetimeIndex:
    """Parse a sequence of bar timestamp values into a UTC DatetimeIndex.

    Supports:
    - int/float Unix seconds (Finbot/Hyperliquid production format)
    - int/float Unix milliseconds (auto-detected for large values)
    - ISO-8601 strings
    - Python ``datetime`` / ``pandas.Timestamp``

    Args:
        values: A list, tuple, or pandas Series of timestamp values. All
            values should be of a single kind.

    Returns:
        A timezone-aware (UTC) DatetimeIndex.
    """
    first = values[0]
    if isinstance(first, bool) or not isinstance(first, (int, float)):
        return pd.DatetimeIndex(pd.to_datetime(values, utc=True))
    unit = "ms" if abs(float(first)) >= MS_THRESHOLD else "s"
    return pd.DatetimeIndex(pd.to_datetime(values, unit=unit, utc=True))
