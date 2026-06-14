"""PandasBarFrameConverter — pandas implementation of BarFrameConverter."""

import pandas as pd

from finbar.core.domain.interfaces.bar_frame_converter import BarFrameConverter


class PandasBarFrameConverter(BarFrameConverter):
    """Convert OHLCV bar dictionaries to and from pandas DataFrames."""

    def bars_to_frame(self, bars: list[dict]) -> pd.DataFrame:
        """Convert list of OHLCV bar dicts to a DataFrame with datetime index."""
        if isinstance(bars, pd.DataFrame):
            raise TypeError(
                "bars_to_frame expects a list of dicts, got DataFrame"
            )
        df = pd.DataFrame(bars)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
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
        records = df.to_dict(orient="records")
        # Replace NaN with None for JSON safety. This is done on the records
        # list rather than via df.where(pd.notna(df), None), which would copy
        # the entire DataFrame into object dtype and perform a redundant
        # element-wise pass. Only columns that actually contain NaN are
        # touched; float('nan') is the only value not equal to itself.
        nan_columns = df.columns[df.isna().any()].tolist()
        if nan_columns:
            for record in records:
                for col in nan_columns:
                    value = record[col]
                    if value != value:  # NaN check
                        record[col] = None
        return records
