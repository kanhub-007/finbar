"""Tests for PandasBarFrameConverter round-trip and NaN handling."""

import math

from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)


def _bars() -> list[dict]:
    return [
        {
            "timestamp": "2024-01-02T00:00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
            "sma_20": 99.0,
        },
        {
            "timestamp": "2024-01-03T00:00:00",
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1500,
            "sma_20": 99.5,
        },
    ]


class TestFrameToBars:
    def test_round_trip_preserves_values(self):
        converter = PandasBarFrameConverter()
        df = converter.bars_to_frame(_bars())
        out = converter.frame_to_bars(df)
        assert len(out) == 2
        assert out[0]["close"] == 100.5
        assert out[1]["volume"] == 1500

    def test_nan_columns_become_none(self):
        """Regression: NaN must be converted to None (JSON-safe).

        Previously done via df.where(pd.notna(df), None), which copies the
        entire DataFrame. Now done on the records list, touching only the
        columns that actually contain NaN.
        """
        converter = PandasBarFrameConverter()
        df = converter.bars_to_frame(_bars())
        # Introduce NaN in an indicator column for the first bar only.
        df.loc[df.index[0], "sma_20"] = float("nan")
        out = converter.frame_to_bars(df)

        assert out[0]["sma_20"] is None
        assert out[1]["sma_20"] == 99.5

    def test_columns_without_nan_are_untouched(self):
        converter = PandasBarFrameConverter()
        df = converter.bars_to_frame(_bars())
        out = converter.frame_to_bars(df)
        # close has no NaN; values are real floats.
        assert out[0]["close"] == 100.5
        assert not any(math.isnan(v) for v in (b["close"] for b in out))
