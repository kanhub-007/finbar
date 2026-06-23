"""Contract tests for Scenario 5: WindowedIndicatorState preserves real
bar timestamps for session/date-sensitive indicators.

The windowed streaming fallback previously built its DataFrame index from
``pd.date_range("2024-01-01", ...)``. That discards real candle
timestamps, so any indicator computed through the fallback could be
silently wrong if it later began depending on calendar/session semantics.
These tests lock the fix: real timestamps are preserved, date boundaries
survive, and missing timestamps fail clearly instead of silently
fabricating dates.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pandas as pd
import pytest

from finbar_strategy_runtime.indicators.streaming.windowed_indicator_state import (
    BatchedWindowedState,
    WindowedIndicatorState,
)

# ── Scenario 5: real timestamps are preserved ───────────────────────────────


class TestWindowedStatePreservesTimestamps:
    """Black-box: the buffer frame index reflects real bar timestamps."""

    def test_int_second_timestamps_become_utc_index(self):
        """Numeric timestamps are parsed as Unix seconds (Finbot format)."""
        bars = [
            {
                "timestamp": 1781566200,
                "open": 1.0,
                "high": 2.0,
                "low": 1.0,
                "close": 2.0,
                "volume": 10.0,
            },
            {
                "timestamp": 1781652600,
                "open": 2.0,
                "high": 3.0,
                "low": 2.0,
                "close": 3.0,
                "volume": 11.0,
            },
        ]
        state = WindowedIndicatorState(name="vp_poc", maxlen=10)
        for bar in bars:
            state.update(bar)

        frame = state.to_frame()

        assert frame.index[0] == pd.Timestamp(1781566200, unit="s", tz="UTC")
        assert frame.index[1] == pd.Timestamp(1781652600, unit="s", tz="UTC")

    def test_iso_string_timestamps_become_utc_index(self):
        """ISO-8601 string timestamps are parsed as UTC."""
        bars = [
            {
                "timestamp": "2026-06-07T10:00:00",
                "open": 1.0,
                "high": 2.0,
                "low": 1.0,
                "close": 2.0,
                "volume": 10.0,
            },
            {
                "timestamp": "2026-06-08T10:00:00",
                "open": 2.0,
                "high": 3.0,
                "low": 2.0,
                "close": 3.0,
                "volume": 11.0,
            },
        ]
        state = WindowedIndicatorState(name="vp_poc", maxlen=10)
        for bar in bars:
            state.update(bar)

        frame = state.to_frame()

        assert frame.index[0] == pd.Timestamp("2026-06-07 10:00:00", tz="UTC")
        assert frame.index[1] == pd.Timestamp("2026-06-08 10:00:00", tz="UTC")

    def test_python_datetime_timestamps_become_utc_index(self):
        """Python datetime timestamps are parsed as UTC."""
        bars = [
            {
                "timestamp": datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
                "open": 1.0,
                "high": 2.0,
                "low": 1.0,
                "close": 2.0,
                "volume": 10.0,
            },
            {
                "timestamp": datetime(2026, 6, 8, 10, 0, tzinfo=UTC),
                "open": 2.0,
                "high": 3.0,
                "low": 2.0,
                "close": 3.0,
                "volume": 11.0,
            },
        ]
        state = WindowedIndicatorState(name="vp_poc", maxlen=10)
        for bar in bars:
            state.update(bar)

        frame = state.to_frame()

        assert frame.index[0] == pd.Timestamp("2026-06-07 10:00:00", tz="UTC")
        assert frame.index[1] == pd.Timestamp("2026-06-08 10:00:00", tz="UTC")

    def test_date_boundary_preserved_when_bars_cross_midnight(self):
        """The index date changes when input timestamps cross midnight."""
        # 86400 s apart = exactly one calendar day later
        bars = [
            {
                "timestamp": 1781566200,
                "open": 1.0,
                "high": 2.0,
                "low": 1.0,
                "close": 2.0,
                "volume": 10.0,
            },
            {
                "timestamp": 1781566200 + 86400,
                "open": 2.0,
                "high": 3.0,
                "low": 2.0,
                "close": 3.0,
                "volume": 11.0,
            },
        ]
        state = WindowedIndicatorState(name="vp_poc", maxlen=10)
        for bar in bars:
            state.update(bar)

        frame = state.to_frame()

        assert str(frame.index[0].date()) != "2024-01-01"
        assert frame.index[0].date() != frame.index[1].date()

    def test_no_fabricated_2024_index_when_real_timestamps_present(self):
        """No fabricated ``2024-01-01`` index leaks through when bars carry
        real timestamps."""
        bars = [
            {
                "timestamp": 1781566200,
                "open": 1.0,
                "high": 2.0,
                "low": 1.0,
                "close": 2.0,
                "volume": 10.0,
            },
        ]
        state = WindowedIndicatorState(name="vp_poc", maxlen=10)
        state.update(bars[0])
        state.update(bars[0])  # second bar so buffer >= 2

        frame = state.to_frame()

        assert str(frame.index[0].date()) != "2024-01-01"


# ── Scenario 5: missing timestamps fail clearly for all indicators ──────────


class TestWindowedStateMissingTimestamps:
    """Windowed indicators must not silently fabricate dates."""

    @pytest.mark.parametrize(
        "name",
        [
            "vp_poc",
            "vp_vah",
            "vp_val",
            "mp_poc",
            "near_vah",
            "rejection_from_edge",
            "value_area_width_pct",
            "acceptance_into_value",
            "value_area_migration",
        ],
    )
    def test_session_sensitive_missing_timestamp_raises(self, name):
        """A session-sensitive indicator with no timestamps raises clearly."""
        bars = [
            {
                "open": 1.0,
                "high": 2.0,
                "low": 1.0,
                "close": 2.0,
                "volume": 10.0,
            },
            {
                "open": 2.0,
                "high": 3.0,
                "low": 2.0,
                "close": 3.0,
                "volume": 11.0,
            },
        ]
        state = WindowedIndicatorState(name=name, maxlen=10)

        with pytest.raises(ValueError, match="timestamp"):
            for bar in bars:
                state.update(bar)

    def test_non_session_indicator_missing_timestamp_raises(self):
        """A non-session-sensitive indicator still requires timestamps.

        Fabricating dates for any metric is banned because it can make
        correctness depend on hidden fallback behaviour.
        """
        bars = [
            {
                "open": 1.0,
                "high": 2.0,
                "low": 1.0,
                "close": 2.0,
                "volume": 10.0,
            },
            {
                "open": 2.0,
                "high": 3.0,
                "low": 2.0,
                "close": 3.0,
                "volume": 11.0,
            },
        ]
        state = WindowedIndicatorState(name="bearish_fvg", maxlen=10)

        with pytest.raises(ValueError, match="timestamp"):
            for bar in bars:
                state.update(bar)


# ── Scenario 5: numeric millisecond timestamps ──────────────────────────────


class TestWindowedStateMillisecondTimestamps:
    """Numeric timestamps large enough to be milliseconds are parsed as ms.

    Production bars are int seconds (Finbot/Hyperliquid). To avoid a
    silent unit misparse that would corrupt session grouping, large
    numeric values (>= 1e11) are treated as milliseconds.
    """

    def test_large_numeric_treated_as_milliseconds(self):
        sec = 1781566200
        ms = sec * 1000
        bars = [
            {
                "timestamp": ms,
                "open": 1.0,
                "high": 2.0,
                "low": 1.0,
                "close": 2.0,
                "volume": 10.0,
            },
            {
                "timestamp": ms + 86_400_000,
                "open": 2.0,
                "high": 3.0,
                "low": 2.0,
                "close": 3.0,
                "volume": 11.0,
            },
        ]
        state = WindowedIndicatorState(name="vp_poc", maxlen=10)
        for bar in bars:
            state.update(bar)

        frame = state.to_frame()

        assert frame.index[0] == pd.Timestamp(sec, unit="s", tz="UTC")
        assert frame.index[1].date() != frame.index[0].date()


# ── Scenario 1 (spec 2026-06-23): BatchedWindowedState + production guard ────


class TestBatchedStateRejectsMissingTimestamps:
    """The shared batched ring buffer must also reject missing timestamps."""

    def test_batched_missing_timestamp_raises(self):
        """BatchedWindowedState raises before any metric is computed."""
        state = BatchedWindowedState(
            names=["bearish_fvg", "demand_zone_score"], maxlen=10
        )
        bars = [
            {"open": 1.0, "high": 2.0, "low": 1.0, "close": 2.0, "volume": 10.0},
            {"open": 2.0, "high": 3.0, "low": 2.0, "close": 3.0, "volume": 11.0},
        ]

        with pytest.raises(ValueError, match="timestamp"):
            for bar in bars:
                state.update(bar)


class TestNoSyntheticTimestampFallbackInProduction:
    """Guard: no production source fabricates a date index for metrics.

    A synthetic ``date_range(...)`` fallback for missing timestamps would
    make session/date-sensitive metrics silently wrong, which is banned by
    the spec's strictness contract.
    """

    def test_no_fallback_origin_constant_in_runtime_package(self):
        runtime_root = pathlib.Path(__file__).resolve().parents[2]
        offenders: list[str] = []
        for path in runtime_root.rglob("*.py"):
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if "_FALLBACK_ORIGIN" in text:
                offenders.append(str(path))
        assert not offenders, (
            "Synthetic timestamp fallback constant found: " + ", ".join(offenders)
        )

    def test_no_fabricated_2024_date_range_in_runtime_package(self):
        runtime_root = pathlib.Path(__file__).resolve().parents[2]
        offenders: list[str] = []
        for path in runtime_root.rglob("*.py"):
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if 'pd.date_range("2024-01-01"' in text:
                offenders.append(str(path))
        assert not offenders, (
            "Fabricated 2024-01-01 date_range found: " + ", ".join(offenders)
        )
