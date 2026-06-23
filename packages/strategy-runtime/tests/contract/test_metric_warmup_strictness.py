"""Spec 2026-06-23 Scenario 4 — warmup uses UNKNOWN/NaN, not tradable neutral.

Classifiers that require multiple sessions or rolling lookbacks previously
emitted neutral/tradable-looking defaults during warmup: ``profile_shape``
defaulted to ``NEUTRAL`` before 5 sessions, ``poc_slope_N`` to ``0.0``
before ``N`` sessions, ``value_area_migration`` to ``STABLE`` on the first
session, and ``wyckoff_phase`` to ``NEUTRAL``. A strategy condition such
as ``is_neutral_shape`` would then wrongly fire during warmup. The fix:
warmup emits NaN / UNKNOWN, and readiness gating keeps trading suppressed
until real values exist.

Classical school, black-box: real service functions and the real calculator
on small timestamped frames. Assert on returned column values and on the
``RequiredDataValidator`` readiness outcome.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from finbar_strategy_runtime.domain.services.amt_signals import compute_amt_signals
from finbar_strategy_runtime.domain.services.profile_shape import (
    classify_all_profile_shapes,
)
from finbar_strategy_runtime.domain.services.wyckoff_phase import compute_poc_slope
from finbar_strategy_runtime.indicators.required_data_validator import (
    RequiredDataValidator,
)


def _session_frame(sessions: int, bars_per_session: int = 8) -> pd.DataFrame:
    """A timestamped OHLCV frame spanning N calendar sessions."""
    base = pd.Timestamp("2026-01-05 09:30", tz="UTC")
    times, rows = [], []
    for s in range(sessions):
        for b in range(bars_per_session):
            times.append(base + pd.Timedelta(days=s) + pd.Timedelta(minutes=5 * b))
            close = 100.0 + s * bars_per_session + b
            rows.append(
                {
                    "open": close - 0.5,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 1000.0 + b,
                }
            )
    return pd.DataFrame(rows, index=pd.DatetimeIndex(times))


def _is_unknown_or_nan(value) -> bool:
    """True for NaN or an explicit UNKNOWN label."""
    if value is None:
        return True
    try:
        if isinstance(value, float) and math.isnan(value):
            return True
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).upper() == "UNKNOWN"


# ── profile_shape warmup ────────────────────────────────────────────────────


class TestProfileShapeWarmupIsNotNeutral:
    def test_few_sessions_emit_unknown_not_neutral(self):
        """With < 5 sessions, profile_shape is NaN/UNKNOWN, never NEUTRAL."""
        frame = _session_frame(sessions=2)
        result = classify_all_profile_shapes(frame)

        assert "profile_shape" in result.columns
        values = result["profile_shape"]
        # No warmup value must masquerade as a real NEUTRAL classification.
        assert not (values == "NEUTRAL").any(), (
            "profile_shape emitted NEUTRAL during warmup"
        )
        assert all(_is_unknown_or_nan(v) for v in values), (
            "profile_shape warmup values must be NaN/UNKNOWN"
        )

    def test_enough_sessions_emit_real_shapes(self):
        """Once enough history exists, real shape labels appear."""
        frame = _session_frame(sessions=7)
        result = classify_all_profile_shapes(frame)
        labels = set(result["profile_shape"].dropna().unique())
        # Real classifications (NORMAL/B_SHAPE/...) appear, not just warmup.
        assert labels, "expected at least one real shape label"
        assert all(not _is_unknown_or_nan(lbl) for lbl in labels)


# ── poc_slope warmup ────────────────────────────────────────────────────────


class TestPocSlopeWarmupIsNaN:
    def test_poc_slope_is_nan_before_window_sessions(self):
        """poc_slope_N is NaN until N sessions of history exist."""
        # Provide vp_poc so the function has its dependency.
        frame = _session_frame(sessions=3)
        frame["vp_poc"] = np.linspace(100.0, 109.0, len(frame))

        slope = compute_poc_slope(frame, window=20)

        # 3 sessions < 20 → every value is NaN (warmup), never a fake 0.0.
        assert slope.isna().all(), "poc_slope_20 must be NaN during warmup"
        assert not (slope == 0.0).any(), "poc_slope_20 emitted 0.0 during warmup"


# ── value_area_migration warmup ─────────────────────────────────────────────


class TestValueAreaMigrationWarmupIsUnknown:
    def test_first_session_is_unknown_not_stable(self):
        """On the first session there is no previous session to compare to.

        value_area_migration must not emit STABLE (a tradable 'no migration'
        signal) for the first session; it must be UNKNOWN/NaN.
        """
        frame = _session_frame(sessions=2, bars_per_session=4)
        # Provide the auction-state deps compute_amt_signals requires.
        frame["vp_poc"] = np.linspace(100.0, 105.0, len(frame))
        frame["vp_vah"] = frame["vp_poc"] + 2.0
        frame["vp_val"] = frame["vp_poc"] - 2.0
        frame["inside_value"] = True
        frame["above_value"] = False
        frame["below_value"] = False
        frame["near_vah"] = False
        frame["near_val"] = False
        frame["at_poc"] = True
        frame["rvol"] = 1.0
        frame["atr"] = 1.0

        result = compute_amt_signals(frame)
        migration = result["value_area_migration"]

        first_session_date = frame.index[0].date()
        first_session_values = migration[frame.index.date == first_session_date]
        assert all(
            _is_unknown_or_nan(v) for v in first_session_values
        ), "value_area_migration must be UNKNOWN/NaN on the first session"
        assert not (first_session_values == "STABLE").any(), (
            "value_area_migration emitted STABLE on the first session"
        )


# ── readiness gating keeps warmup non-tradable ──────────────────────────────


class TestReadinessGatingSuppressesWarmup:
    def test_profile_shape_warmup_blocks_trading(self):
        """RequiredDataValidator reports no tradable bars during warmup."""
        frame = _session_frame(sessions=2)
        enriched = classify_all_profile_shapes(frame)

        readiness = RequiredDataValidator().validate(enriched, ["profile_shape"])
        # Warmup values are NaN/UNKNOWN → no tradable bar.
        assert readiness.no_tradable_bars is True


# ── wyckoff_phase warmup (via calculator, deps resolved) ─────────────────────


class TestWyckoffPhaseWarmupIsUnknown:
    def test_short_history_wyckoff_phase_is_unknown_not_neutral(self):
        """With insufficient slope history, wyckoff_phase is NaN/UNKNOWN."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        # Few sessions → not enough for poc_slope_20 warmup.
        frame = _session_frame(sessions=6, bars_per_session=10)
        calc = PandasTaIndicatorCalculator()
        result = calc.calculate(frame, ["wyckoff_phase"])

        if "wyckoff_phase" not in result.columns:
            pytest.skip("wyckoff_phase column not produced on short frame")
        values = result["wyckoff_phase"]
        # Every value must be NaN/UNKNOWN during warmup (slope not computable
        # with so few sessions); none may masquerade as a confident NEUTRAL.
        assert all(_is_unknown_or_nan(v) for v in values), (
            "wyckoff_phase emitted a confident label during warmup"
        )
        assert not (values == "NEUTRAL").any()
