"""Spec 2026-06-23 Scenario 3 — metric handlers fail when deps are absent.

Pure AMT/Wyckoff/VP service functions previously either raised an opaque
``KeyError`` mid-computation or silently substituted neutral/default
values (``NEUTRAL``, ``STABLE``, ``False``, ``0.0``, all-NaN) when their
required dependency columns were missing. The strictness contract bans
silent substitution: missing required dependencies must raise a clear
``MetricDependencyError`` naming the missing column.

Classical school, black-box: real service functions on real (small)
DataFrames. Assert on raised exception type/message and on the absence of
silent default output — never on internal helper calls.
"""

from __future__ import annotations

import pandas as pd
import pytest

from finbar_strategy_runtime.domain.entities.metric_dependency_error import (
    MetricDependencyError,
)
from finbar_strategy_runtime.domain.services.amt_signals import compute_amt_signals
from finbar_strategy_runtime.domain.services.auction_state import (
    classify_auction_state,
)
from finbar_strategy_runtime.domain.services.volume_profile import (
    compute_rolling_vp,
)
from finbar_strategy_runtime.domain.services.wyckoff_phase import (
    classify_wyckoff_phase,
)


def _ohlcv_frame(sessions: int = 3, bars_per_session: int = 8) -> pd.DataFrame:
    """A timestamped OHLCV frame with NO indicator columns."""
    base = pd.Timestamp("2026-01-05 09:30", tz="UTC")
    times = []
    row_dicts = []
    for s in range(sessions):
        for b in range(bars_per_session):
            ts = base + pd.Timedelta(days=s) + pd.Timedelta(minutes=5 * b)
            times.append(ts)
            close = 100.0 + s * bars_per_session + b
            row_dicts.append(
                {
                    "open": close - 0.5,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 1000.0 + b,
                }
            )
    return pd.DataFrame(row_dicts, index=pd.DatetimeIndex(times))


# ── Scenario 3: missing required deps raise a clear error ──────────────────


class TestAuctionStateRequiresVolumeProfileDeps:
    def test_classify_auction_state_without_vp_raises_dependency_error(self):
        frame = _ohlcv_frame()

        with pytest.raises(MetricDependencyError) as exc_info:
            classify_auction_state(frame)

        message = str(exc_info.value)
        assert "vp_vah" in message or "vp_val" in message or "vp_poc" in message
        assert "near_vah" in exc_info.value.metric_name or exc_info.value.metric_name

    def test_classify_auction_state_does_not_emit_silent_booleans(self):
        """No NaN-derived near_vah/inside_value columns leak out on missing deps."""
        frame = _ohlcv_frame()

        with pytest.raises(MetricDependencyError):
            result = classify_auction_state(frame)
            # If it ever stops raising, it must NOT silently produce booleans.
            assert "near_vah" not in result.columns


class TestAmtSignalsRequireDeps:
    def test_compute_amt_signals_without_deps_raises(self):
        frame = _ohlcv_frame()

        with pytest.raises(MetricDependencyError) as exc_info:
            compute_amt_signals(frame)

        message = str(exc_info.value)
        # poc_rejection / edge_volume_building need these
        assert any(
            col in message
            for col in ("vp_poc", "vp_vah", "vp_val", "atr", "rvol", "near_vah")
        )

    def test_rejection_from_edge_not_silently_false_without_vp(self):
        """rejection_from_edge must not silently read as all-False."""
        frame = _ohlcv_frame()
        with pytest.raises(MetricDependencyError):
            result = compute_amt_signals(frame)
            if "rejection_from_edge" in result.columns:
                assert result["rejection_from_edge"].any()


class TestWyckoffPhaseRequiresDeps:
    def test_classify_wyckoff_phase_without_deps_raises(self):
        frame = _ohlcv_frame()

        with pytest.raises(MetricDependencyError) as exc_info:
            classify_wyckoff_phase(frame)

        message = str(exc_info.value)
        assert any(
            col in message
            for col in (
                "vp_poc",
                "balance_status",
                "profile_shape",
                "rvol",
                "value_area_width_pct",
            )
        )

    def test_wyckoff_phase_not_silently_neutral(self):
        """wyckoff_phase must not silently emit NEUTRAL on missing deps."""
        frame = _ohlcv_frame()
        with pytest.raises(MetricDependencyError):
            result = classify_wyckoff_phase(frame)
            if "wyckoff_phase" in result.columns:
                assert not (result["wyckoff_phase"] == "NEUTRAL").all()


class TestRollingVpRequiresSessionVpDeps:
    def test_compute_rolling_vp_without_vp_raises(self):
        frame = _ohlcv_frame()

        with pytest.raises(MetricDependencyError) as exc_info:
            compute_rolling_vp(frame, window=5)

        message = str(exc_info.value)
        assert "vp_poc" in message or "vp_vah" in message or "vp_val" in message

    def test_rolling_vp_not_silently_all_nan(self):
        """vp_poc_5d must not silently return an all-NaN column."""
        frame = _ohlcv_frame()
        with pytest.raises(MetricDependencyError):
            result = compute_rolling_vp(frame, window=5)
            assert not result["vp_poc_5d"].isna().all()


# ── Also test: normal parser-driven requests still pass ────────────────────


class TestNormalCalculatorRequestsStillPass:
    """Transitive dependency expansion keeps normal requests working.

    When deps ARE available (computed first), the services must not raise.
    """

    def test_near_vah_computes_when_vp_is_resolvable(self):
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        # Near_vah transitively pulls vp_vah/vp_val which are computable from
        # OHLCV + a real datetime index. This must succeed without raising.
        frame = _ohlcv_frame(sessions=6, bars_per_session=10)
        result = calc.calculate(frame, ["near_vah", "inside_value"])
        assert "near_vah" in result.columns
        assert "inside_value" in result.columns
