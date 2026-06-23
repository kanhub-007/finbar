"""Contract tests for Scenario 8: VP-prefix windowed indicator parity.

Verifies that VP-prefix indicators (rvp_*, vp_*Nd, cvp_*Nd) fall back
to windowed recompute and match the batch calculator (loose tolerance).

Note: RVP/CVP indicators have inter-indicator dependencies (require VP
columns). The simple windowed fallback cannot satisfy these — they need
dedicated streaming state or a dependency-aware recompute. These are
deferred to a later slice (ADR-1: true sliding-window VP).
"""

import math

import pytest

from .test_streaming_sma_parity import _bars_to_frame, _make_deterministic_bars


class TestVpWindowedParity:
    """Scenario 8: VP-prefix indicators match batch via windowed fallback."""

    # Direct VP indicators work with windowed recompute (no dependencies)
    DIRECT_VP_INDICATORS = [
        ("vp_poc_10d", 100),
        ("vp_vah_10d", 100),
        ("vp_val_10d", 100),
    ]

    # RVP/CVP have inter-indicator dependencies — deferred
    DEFERRED_INDICATORS = [
        "rvp_poc_48",
        "rvp_vah_96",
        "rvp_val_24",
        "cvp_poc_5d",
        "cvp_vah_5d",
    ]

    @pytest.mark.parametrize("indicator,bar_count", DIRECT_VP_INDICATORS)
    def test_vp_windowed_matches_batch(self, indicator, bar_count):
        """Streaming VP-prefix indicator latest ≈ batch last-row."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        bars = _make_deterministic_bars(bar_count, seed=8)
        batch_last = (
            PandasTaIndicatorCalculator()
            .calculate(_bars_to_frame(bars), [indicator])
            .iloc[-1]
            .to_dict()
        )

        engine = StreamingIndicatorEngine(indicators=[indicator])
        for b in bars:
            engine.update(b)

        got = engine.latest().values.get(indicator, float("nan"))
        expected = batch_last.get(indicator, float("nan"))

        if math.isnan(got) and math.isnan(expected):
            return

        # Loose tolerance for windowed recompute
        assert math.isclose(
            got, expected, rel_tol=1e-7, abs_tol=1e-9
        ), (
            f"{indicator}: streaming={got}, batch={expected}, "
            f"diff={abs(got - expected)}"
        )

    @pytest.mark.skip(
        reason="RVP/CVP have inter-indicator deps — needs dedicated state "
        "or dependency-aware recompute (deferred to later slice per ADR-1)"
    )
    @pytest.mark.parametrize(
        "indicator", DEFERRED_INDICATORS
    )
    def test_rvp_cvp_deferred(self, indicator):
        """RVP/CVP parity — deferred to later slice."""
        pass
