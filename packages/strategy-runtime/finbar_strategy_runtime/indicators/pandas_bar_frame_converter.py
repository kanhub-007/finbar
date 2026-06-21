"""PandasBarFrameConverter — pandas implementation of BarFrameConverter."""

import pandas as pd

from finbar_strategy_runtime.domain.interfaces.bar_frame_converter import (
    BarFrameConverter,
)
from finbar_strategy_runtime.indicators._bar_timestamp import (
    parse_bar_timestamps,
)


class PandasBarFrameConverter(BarFrameConverter):
    """Convert OHLCV bar dictionaries to and from pandas DataFrames."""

    def bars_to_frame(self, bars: list[dict]) -> pd.DataFrame:
        """Convert list of OHLCV bar dicts to a DataFrame with datetime index.

        Timestamps are parsed as Unix seconds by default
        (Finbot/Hyperliquid production format), with millisecond
        auto-detection for large numeric values, plus ISO-8601 strings
        and Python datetimes.
        """
        if isinstance(bars, pd.DataFrame):
            raise TypeError("bars_to_frame expects a list of dicts, got DataFrame")
        df = pd.DataFrame(bars)
        if "timestamp" in df.columns:
            df["timestamp"] = parse_bar_timestamps(df["timestamp"].tolist())
            df = df.set_index("timestamp").sort_index()
        return df

    def frame_to_bars(self, frame: pd.DataFrame) -> list[dict]:
        """Convert a DataFrame back to JSON-serializable bar dictionaries."""
        df = frame.reset_index()
        datetime_cols = df.select_dtypes(
            include=["datetime64[ns]", "datetime64[ns, UTC]"]
        ).columns
        for col in datetime_cols:
            df[col] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%S")
        # Replace NaN with None using a single vectorised pass.
        # ``df.astype(object).where(pd.notna(df), None)`` converts NaN to
        # None in one shot, avoiding the previous nested per-record loop.
        nan_columns = df.columns[df.isna().any()].tolist()
        if nan_columns:
            df[nan_columns] = (
                df[nan_columns].astype(object).where(df[nan_columns].notna(), None)
            )
        return df.to_dict(orient="records")
