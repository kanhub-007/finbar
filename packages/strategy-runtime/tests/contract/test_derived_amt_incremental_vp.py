"""Spec 2026-06-23 Scenario 6 — derived AMT streaming metrics get incremental
VP dependencies automatically.

When a strategy requests a derived AMT metric (e.g. ``near_vah``) without
explicitly requesting ``vp_poc/vp_vah/vp_val``, the streaming engine must
still detect the transitive VP dependency and inject the incremental
expanding-session VP state. Otherwise the windowed fallback computes VP on
a truncated trailing window (when the session is longer than the window),
which diverges from the causal prefix oracle that uses the full
expanding-from-session-open profile.

Classical school, black-box: real streaming engine and real batch prefix
oracle on deterministic timestamped bars. We assert streaming values equal
the prefix oracle at deep-in-session rows where truncation would otherwise
show up.
"""

from __future__ import annotations

import math

import pandas as pd

from finbar_strategy_runtime.indicators.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)
from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
    StreamingIndicatorEngine,
)
from tests.support.metric_value_assertions import assert_equivalent_metric_value


def _long_session_bars(bars: int = 90) -> list[dict]:
    """5-minute bars all on one calendar date (one long session > 50 bars).

    A long session exposes window truncation: near_vah's windowed fallback
    uses a 50-bar window, so rows beyond 50 in the session would lose the
    session-open bars and compute VP on a truncated prefix.
    """
    base = pd.Timestamp("2026-01-05 09:30", tz="UTC")
    out = []
    for i in range(bars):
        ts = base + pd.Timedelta(minutes=5 * i)
        # Varying closes/volume so the volume profile is non-trivial and
        # genuinely shifts as the session expands.
        close = 100.0 + 2.0 * math.sin(i / 8.0) + (i % 3)
        out.append(
            {
                "timestamp": int(ts.timestamp()),
                "open": close - 0.4,
                "high": close + 1.2 + (i % 2),
                "low": close - 1.2 - (i % 2),
                "close": close,
                "volume": 500.0 + 50.0 * (i % 7),
            }
        )
    return out


def _prefix_oracle_value(metric: str, bars: list[dict], index: int):
    """Batch-calculate *metric* on bars[:index+1] and return the last-row value."""
    prefix = bars[: index + 1]
    frame = PandasBarFrameConverter().bars_to_frame(prefix)
    enriched = PandasTaIndicatorCalculator().calculate(frame, [metric])
    return enriched.iloc[-1][metric]


class TestDerivedAmtGetsIncrementalVp:
    """Derived AMT metrics match the prefix oracle without explicit vp_*."""

    def test_near_vah_matches_prefix_oracle_deep_in_session(self):
        """near_vah (no vp_* requested) equals the expanding-session oracle.

        Sampled at rows 60 and 75 — past the 50-bar window boundary, where a
        truncated window would otherwise diverge from the full-session prefix.
        """
        bars = _long_session_bars(90)
        engine = StreamingIndicatorEngine(["near_vah"])
        samples = {60, 75}

        for index, bar in enumerate(bars):
            latest = engine.update(bar)
            if index not in samples:
                continue
            got = latest.values.get("near_vah")
            expected = _prefix_oracle_value("near_vah", bars, index)
            assert_equivalent_metric_value(got, expected, "near_vah")

    def test_value_area_width_pct_matches_prefix_oracle_deep_in_session(self):
        """value_area_width_pct (float, derived from vp_vah/vp_val) matches.

        A strictly numeric derived AMT metric gives a clean tolerance-based
        comparison with no bool/float representation ambiguity.
        """
        bars = _long_session_bars(90)
        engine = StreamingIndicatorEngine(["value_area_width_pct"])
        samples = {60, 75}

        for index, bar in enumerate(bars):
            latest = engine.update(bar)
            if index not in samples:
                continue
            got = latest.values.get("value_area_width_pct")
            expected = _prefix_oracle_value("value_area_width_pct", bars, index)
            assert_equivalent_metric_value(
                got, expected, "value_area_width_pct"
            )

    def test_rejection_from_edge_matches_prefix_oracle_deep_in_session(self):
        """rejection_from_edge (no vp_* requested) equals the prefix oracle."""
        bars = _long_session_bars(90)
        engine = StreamingIndicatorEngine(["rejection_from_edge", "atr", "rvol"])
        samples = {60, 75}

        for index, bar in enumerate(bars):
            latest = engine.update(bar)
            if index not in samples:
                continue
            got = latest.values.get("rejection_from_edge")
            expected = _prefix_oracle_value("rejection_from_edge", bars, index)
            assert_equivalent_metric_value(
                got, expected, "rejection_from_edge"
            )

    def test_engine_creates_session_vp_for_transitive_dep(self):
        """Requesting near_vah alone must still instantiate the VP state."""
        engine = StreamingIndicatorEngine(["near_vah"])
        assert engine._session_vp is not None, (
            "derived AMT metric must auto-instantiate incremental session VP"
        )
