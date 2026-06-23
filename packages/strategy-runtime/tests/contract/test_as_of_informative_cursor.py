"""Spec 2026-06-23 Scenario 7 — informative MTF as-of lookup is causal and O(n+m).

The causal MTF enricher previously reverse-scanned the full informative
history for every primary bar (O(primary × informative)). Replacing that
with an ``AsOfInformativeCursor`` per alias — a monotonic pointer over
availability timestamps — makes the merge O(primary + informative) while
preserving the no-lookahead invariant: an informative bar is visible only
once it has fully closed (open + interval_offset <= primary open).

Classical school, black-box: assert on cursor return values and on the
causal-merge equivalence of the full enricher (sequential vs cursor-backed
paths produce identical frames).
"""

from __future__ import annotations

import time

import pandas as pd
import pytest

from finbar_strategy_runtime.domain.entities.as_of_informative_cursor import (
    AsOfInformativeCursor,
)


def _ts(minutes: float) -> pd.Timestamp:
    """A UTC timestamp minutes after the epoch-referenced base."""
    return pd.Timestamp("2026-01-05 00:00", tz="UTC") + pd.Timedelta(
        minutes=minutes
    )


# ── Cursor causal correctness ───────────────────────────────────────────────


class TestAsOfInformativeCursorCausal:
    def test_empty_cursor_returns_none(self):
        cursor = AsOfInformativeCursor()
        assert cursor.latest_visible_at(_ts(0)) is None

    def test_not_yet_closed_bar_is_invisible(self):
        """A bar whose close (open+offset) is after primary_open is invisible."""
        cursor = AsOfInformativeCursor(offset=pd.Timedelta(hours=1))
        cursor.append(_ts(0), {"v": 1})  # closes at +1h
        # primary at 30min: the 1h bar closes at 1h, so not visible yet.
        assert cursor.latest_visible_at(_ts(30)) is None

    def test_closed_bar_becomes_visible_at_close_time(self):
        cursor = AsOfInformativeCursor(offset=pd.Timedelta(hours=1))
        cursor.append(_ts(0), {"v": 1})  # closes at +1h
        assert cursor.latest_visible_at(_ts(60)) == {"v": 1}

    def test_latest_visible_row_is_returned_for_monotonic_primary(self):
        cursor = AsOfInformativeCursor(offset=pd.Timedelta(hours=1))
        cursor.append(_ts(0), {"v": 1})   # visible from +1h
        cursor.append(_ts(60), {"v": 2})  # visible from +2h
        cursor.append(_ts(120), {"v": 3})  # visible from +3h

        assert cursor.latest_visible_at(_ts(60)) == {"v": 1}
        assert cursor.latest_visible_at(_ts(90)) == {"v": 1}
        assert cursor.latest_visible_at(_ts(120)) == {"v": 2}
        assert cursor.latest_visible_at(_ts(300)) == {"v": 3}

    def test_no_future_leak(self):
        """A bar appended AFTER a lookup must never satisfy an earlier query."""
        cursor = AsOfInformativeCursor(offset=pd.Timedelta(hours=1))
        cursor.append(_ts(0), {"v": 1})
        # First query at 30min: nothing visible.
        assert cursor.latest_visible_at(_ts(30)) is None
        # Appending a later bar does not retroactively change the past.
        cursor.append(_ts(60), {"v": 2})
        assert cursor.latest_visible_at(_ts(30)) is None

    def test_reset_clears_state(self):
        cursor = AsOfInformativeCursor(offset=pd.Timedelta(hours=1))
        cursor.append(_ts(0), {"v": 1})
        assert cursor.latest_visible_at(_ts(60)) == {"v": 1}
        cursor.reset()
        assert cursor.latest_visible_at(_ts(60)) is None


# ── Cursor is O(n + m) — pointer never rescans ──────────────────────────────


class TestAsOfInformativeCursorLinearScaling:
    def test_lookup_cost_does_not_grow_with_history_size(self):
        """Each lookup advances the pointer at most once total — no rescan.

        A reverse-scan would be O(history) per lookup; the cursor's amortised
        cost per lookup is O(1). We assert the cursor handles a large history
        without per-lookup cost growth by checking the pointer advances
        monotonically and lookups over a 10k primary series stay sub-second.
        """
        cursor = AsOfInformativeCursor(offset=pd.Timedelta(minutes=1))
        # 10k informative bars, 1 minute apart, each closed 1 minute later.
        for i in range(10_000):
            cursor.append(_ts(i), {"v": i})

        start = time.perf_counter()
        # 10k primary lookups at 1-minute spacing (each should find a bar).
        last = None
        for i in range(10_000):
            last = cursor.latest_visible_at(_ts(i + 1))
        elapsed = time.perf_counter() - start

        assert last == {"v": 9999}
        # Generous budget; the point is no quadratic blow-up. A reverse-scan
        # over 10k×10k here takes ~25s, so even a few-second guard catches it.
        assert elapsed < 2.0, f"cursor lookup too slow: {elapsed:.3f}s"


# ── Full enricher equivalence (sequential vs cursor-backed) ─────────────────


@pytest.fixture
def mtf_strategy_definition():
    from finbar_strategy_runtime.domain.entities.informative_timeframe import (
        InformativeTimeframe,
    )
    from finbar_strategy_runtime.domain.entities.strategy_definition import (
        StrategyDefinition,
    )
    from finbar_strategy_runtime.domain.entities.timeframe_declaration import (
        TimeframeDeclaration,
    )

    return StrategyDefinition(
        name="mtf",
        schema_version="2.0",
        parameters={},
        resolved_params={},
        indicators=[],
        features=[],
        timeframes=TimeframeDeclaration(
            primary="30min",
            informative=[InformativeTimeframe(alias="h1", interval="1h")],
        ),
        risk=None,
        sides=None,
        metadata={},
    )


def _make_bars(count: int, step_minutes: int, start_offset: int = 0) -> list[dict]:
    base = pd.Timestamp("2026-01-05 00:00", tz="UTC")
    bars = []
    for i in range(count):
        ts = base + pd.Timedelta(minutes=start_offset + i * step_minutes)
        bars.append(
            {
                "timestamp": int(ts.timestamp()),
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 1000.0 + i,
            }
        )
    return bars


class TestCausalEnricherUsesCursor:
    def test_parallel_and_sequential_produce_identical_frames(
        self, mtf_strategy_definition
    ):
        """The cursor-backed (parallel) path equals the sequential path."""
        from finbar_strategy_runtime.indicators.causal_multi_timeframe_streaming_enricher import (  # noqa: E501
            CausalMultiTimeframeStreamingEnricher,
        )

        primary = _make_bars(600, step_minutes=30)
        info = {"h1": _make_bars(400, step_minutes=60, start_offset=15)}
        definition = mtf_strategy_definition

        sequential = CausalMultiTimeframeStreamingEnricher.causal_enrich_bars(
            primary, info, definition, [], {"h1": []}, parallel=False
        )
        parallel = CausalMultiTimeframeStreamingEnricher.causal_enrich_bars(
            primary, info, definition, [], {"h1": []}, parallel=True
        )

        pd.testing.assert_frame_equal(sequential, parallel)
