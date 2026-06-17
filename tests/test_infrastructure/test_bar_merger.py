"""Unit tests for the timeframe bar merger (no-lookahead alignment).

Regression coverage for the interval-offset parser: previously only a small
hardcoded set of intervals (5min, 30min, 1h, 1d, 1w) received a non-zero
availability offset, so every other supported interval (5m, 15m, 4h, ...)
silently received a zero offset and leaked future information into earlier
bars.
"""

import numpy as np
import pandas as pd
import pytest
from finbar_strategy_runtime.indicators.bar_merger import (
    interval_offset,
    merge_timeframes,
)


def _primary_frame(timestamps):
    return pd.DataFrame(
        {"close": np.arange(len(timestamps), dtype=float)},
        index=pd.to_datetime(timestamps),
    )


class TestIntervalOffset:
    @pytest.mark.parametrize(
        "interval,expected",
        [
            ("5m", pd.Timedelta(minutes=5)),
            ("5min", pd.Timedelta(minutes=5)),
            ("15m", pd.Timedelta(minutes=15)),
            ("15min", pd.Timedelta(minutes=15)),
            ("30m", pd.Timedelta(minutes=30)),
            ("1h", pd.Timedelta(hours=1)),
            ("4h", pd.Timedelta(hours=4)),
            ("1d", pd.Timedelta(days=1)),
            ("1w", pd.Timedelta(weeks=1)),
        ],
    )
    def test_known_intervals_parse(self, interval, expected):
        # Previously 5m/15m/4h/etc. fell through to Timedelta(0).
        assert interval_offset(interval) == expected

    @pytest.mark.parametrize("interval", ["4h", "15m", "15min", "5m", "2h"])
    def test_previously_broken_intervals_are_nonzero(self, interval):
        """All supported intervals must shift availability forward."""
        assert interval_offset(interval) > pd.Timedelta(0)

    @pytest.mark.parametrize("interval", ["", "monthly", "abc", "h"])
    def test_unknown_interval_raises(self, interval):
        # A zero offset would silently enable lookahead bias; raise instead.
        with pytest.raises(ValueError):
            interval_offset(interval)


class TestNoLookaheadMerge:
    def test_4h_informative_not_visible_within_its_own_window(self):
        """A 4h informative bar must not be visible to earlier 1h bars.

        Previously the 4h offset was silently 0, so the full 4h bar was
        aligned as-of its start timestamp — leaking the bar's value to the
        1h bars that precede its close.
        """
        primary = _primary_frame(
            [
                "2024-01-01 00:00",  # bar 0
                "2024-01-01 01:00",  # bar 1
                "2024-01-01 02:00",  # bar 2
                "2024-01-01 03:00",  # bar 3
                "2024-01-01 04:00",  # bar 4 — 4h bar [00:00,04:00) completes here
            ]
        )
        informative = pd.DataFrame(
            {"trend": [10.0, 20.0]},
            index=pd.to_datetime(["2024-01-01 00:00", "2024-01-01 04:00"]),
        )
        result = merge_timeframes(primary, informative, "4h")

        # The first 4h bar (value 10) is only safe to consume at 04:00.
        # Bars 0..3 must NOT see it yet (NaN); bar 4 may.
        assert pd.isna(result.loc[pd.Timestamp("2024-01-01 00:00"), "trend_4h"])
        assert pd.isna(result.loc[pd.Timestamp("2024-01-01 03:00"), "trend_4h"])
        assert result.loc[pd.Timestamp("2024-01-01 04:00"), "trend_4h"] == 10.0

    def test_unknown_interval_raises_during_merge(self):
        primary = _primary_frame(["2024-01-01 00:00", "2024-01-01 01:00"])
        informative = pd.DataFrame(
            {"trend": [1.0]}, index=pd.to_datetime(["2024-01-01 00:00"])
        )
        with pytest.raises(ValueError):
            merge_timeframes(primary, informative, "monthly")
