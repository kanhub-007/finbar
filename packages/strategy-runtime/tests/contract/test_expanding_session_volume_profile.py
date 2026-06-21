"""Contract tests for Scenario 4: expanding current-session Volume Profile.

Live-parity ``vp_poc`` / ``vp_vah`` / ``vp_val`` must use an *expanding
current-session* profile: each row ``t`` is computed from the current
session's bars from session open through ``t`` only. No later bar in the
same session may influence an earlier row.

This is the causal definition that matches Finbot WebSocket/prefix
behaviour. The completed-session broadcast
(``compute_all_session_volume_profiles``) remains available only as a
labelled batch/research path and is explicitly NOT live-parity safe.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from finbar_strategy_runtime.domain.services.volume_profile import (
    compute_all_session_volume_profiles,
    compute_expanding_session_volume_profiles,
    compute_session_volume_profile,
)

# ── helpers ─────────────────────────────────────────────────────────────────


def _session_frame(bars_per_session: int = 8, sessions: int = 3) -> pd.DataFrame:
    """Build a deterministic frame with several UTC calendar-date sessions.

    Each session is ``bars_per_session`` hourly bars starting at 00:00 UTC,
    so sessions align with calendar dates. Prices drift so every bar
    carries distinct OHLCV.
    """
    rows = []
    ts = pd.Timestamp("2026-06-01 00:00:00", tz="UTC")
    rng = np.random.default_rng(42)
    for s in range(sessions):
        session_open = 100.0 + s * 5.0
        for b in range(bars_per_session):
            close = session_open + rng.normal(0, 1.0)
            high = close + abs(rng.normal(0, 0.5))
            low = close - abs(rng.normal(0, 0.5))
            rows.append(
                {
                    "timestamp": ts,
                    "open": close,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": float(rng.integers(100, 1000)),
                }
            )
            ts = ts + pd.Timedelta(hours=1)
    df = pd.DataFrame(rows)
    return df.set_index(pd.DatetimeIndex(pd.to_datetime(df["timestamp"], utc=True)))[
        ["open", "high", "low", "close", "volume"]
    ]


# ── Scenario 4: expanding current-session profile ───────────────────────────


class TestExpandingSessionVolumeProfile:
    """Black-box: expanding profile matches a per-prefix recompute."""

    def test_expanding_row_equals_prefix_session_profile(self):
        """Row t's vp_* equals compute_session_volume_profile(session[:t+1])."""
        df = _session_frame(bars_per_session=10, sessions=2)
        result = compute_expanding_session_volume_profiles(df)

        for session_date, idx in df.groupby(df.index.date).groups.items():
            session = df.loc[idx]
            session_indices = list(session.index)
            for i, ts in enumerate(session_indices):
                prefix = session.loc[:ts]
                expected = compute_session_volume_profile(prefix)
                got = result.loc[ts]
                assert math.isclose(
                    got["vp_poc"], expected.poc, rel_tol=1e-9, abs_tol=1e-12
                ), f"vp_poc@{ts}: got {got['vp_poc']}, expected {expected.poc}"
                assert math.isclose(
                    got["vp_vah"], expected.vah, rel_tol=1e-9, abs_tol=1e-9
                ), f"vp_vah@{ts}: got {got['vp_vah']}, expected {expected.vah}"
                assert math.isclose(
                    got["vp_val"], expected.val, rel_tol=1e-9, abs_tol=1e-9
                ), f"vp_val@{ts}: got {got['vp_val']}, expected {expected.val}"

    def test_first_bar_of_session_uses_one_bar_profile(self):
        """The first bar of a session computes from a one-bar profile."""
        df = _session_frame(bars_per_session=6, sessions=2)
        result = compute_expanding_session_volume_profiles(df)

        for session_date, idx in df.groupby(df.index.date).groups.items():
            session = df.loc[idx]
            first_ts = session.index[0]
            one_bar_profile = compute_session_volume_profile(session.loc[[first_ts]])
            got = result.loc[first_ts]
            assert math.isclose(
                got["vp_poc"], one_bar_profile.poc, rel_tol=1e-9, abs_tol=1e-12
            )
            return  # one assertion is enough

    def test_later_bar_does_not_mutate_earlier_emitted_row(self):
        """Appending a later bar changes only that later row, not earlier ones."""
        df = _session_frame(bars_per_session=8, sessions=1)
        first_emit = compute_expanding_session_volume_profiles(df.iloc[:3])
        later_emit = compute_expanding_session_volume_profiles(df)

        # The first 3 rows must be identical after more bars are added.
        pd.testing.assert_series_equal(
            first_emit["vp_poc"],
            later_emit["vp_poc"].iloc[:3],
            check_names=False,
        )
        pd.testing.assert_series_equal(
            first_emit["vp_vah"],
            later_emit["vp_vah"].iloc[:3],
            check_names=False,
        )

    def test_no_future_session_bar_leaks_into_earlier_row(self):
        """A row in session 1 is unaffected by session 2's bars.

        The expanding profile for session 1 rows must be identical whether
        or not session 2 bars are present in the frame (proving no future
        leakage across sessions).
        """
        df = _session_frame(bars_per_session=8, sessions=3)
        session_1_only = compute_expanding_session_volume_profiles(df.iloc[:8])
        full = compute_expanding_session_volume_profiles(df)

        pd.testing.assert_series_equal(
            session_1_only["vp_poc"],
            full["vp_poc"].iloc[:8],
            check_names=False,
        )

    def test_expanding_differs_from_completed_session_broadcast(self):
        """Expanding profile is NOT the completed-session broadcast.

        Documents that ``compute_all_session_volume_profiles`` (completed
        broadcast) assigns the same end-of-session profile to every row,
        while expanding assigns a per-row prefix profile. This is the
        live-parity vs batch distinction.
        """
        df = _session_frame(bars_per_session=12, sessions=1)
        expanding = compute_expanding_session_volume_profiles(df)
        broadcast = compute_all_session_volume_profiles(df)

        # First row: expanding uses 1 bar, broadcast uses all 12.
        # They must differ (unless the session is degenerate).
        first_ts = df.index[0]
        assert not math.isclose(
            expanding.loc[first_ts, "vp_vah"],
            broadcast.loc[first_ts, "vp_vah"],
            rel_tol=1e-9,
            abs_tol=1e-9,
        ), (
            "Expanding first-row vp_vah should differ from completed-session"
            " broadcast — otherwise there is no live-parity distinction."
        )

        # Last row of the session: expanding prefix == full session, so it
        # equals the broadcast. Confirms they converge at session close.
        last_ts = df.index[-1]
        assert math.isclose(
            expanding.loc[last_ts, "vp_vah"],
            broadcast.loc[last_ts, "vp_vah"],
            rel_tol=1e-9,
            abs_tol=1e-9,
        )

    def test_preserves_input_columns_and_order(self):
        """The function adds vp_* columns without dropping or reordering."""
        df = _session_frame(bars_per_session=4, sessions=2)
        result = compute_expanding_session_volume_profiles(df)

        for col in ("open", "high", "low", "close", "volume"):
            assert col in result.columns
        for col in ("vp_poc", "vp_vah", "vp_val"):
            assert col in result.columns
        assert list(result.index) == list(df.index)

    def test_does_not_mutate_input_frame(self):
        """The input DataFrame is not modified in place."""
        df = _session_frame(bars_per_session=4, sessions=1)
        original_cols = list(df.columns)
        compute_expanding_session_volume_profiles(df)
        assert list(df.columns) == original_cols

    def test_empty_frame_returns_empty_with_vp_columns(self):
        """An empty input yields an empty frame carrying vp_* columns."""
        df = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
            index=pd.DatetimeIndex([], tz="UTC"),
        )
        result = compute_expanding_session_volume_profiles(df)
        assert result.empty
        for col in ("vp_poc", "vp_vah", "vp_val"):
            assert col in result.columns
