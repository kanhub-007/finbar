"""Shared utilities for converting OHLCV bar lists ↔ DataFrames.

Used by use cases that bridge list-of-dict inputs (from MCP/API) to
DataFrame-based calculators and engines.
"""

import pandas as pd


def bars_to_dataframe(bars: list[dict]) -> pd.DataFrame:
    """Convert list of OHLCV bar dicts to a DataFrame with datetime index.

    If a 'timestamp' column is present, it is parsed as datetime and
    used as the index. The result is sorted by timestamp.

    Args:
        bars: List of dicts with OHLCV keys plus optional indicator columns.

    Returns:
        DataFrame indexed by datetime.
    """
    df = pd.DataFrame(bars)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
    return df


def dataframe_to_bars(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame back to a list of JSON-serializable dicts.

    Handles NaN → None and Timestamp → ISO string for JSON compatibility.
    The index is reset to a column before conversion.

    Args:
        df: DataFrame indexed by datetime.

    Returns:
        List of dicts suitable for JSON serialization.
    """
    df = df.reset_index()
    datetime_cols = df.select_dtypes(
        include=["datetime64[ns]", "datetime64[ns, UTC]"]
    ).columns
    for col in datetime_cols:
        df[col] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%S")
    df = df.where(pd.notna(df), None)
    return df.to_dict(orient="records")
