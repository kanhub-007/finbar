"""Contract tests for Scenario 8b: Windowed-default fallback parity.

Verifies that indicators with registered handlers but no hand-written
streaming state fall back to WindowedIndicatorState and produce correct
values matching the batch calculator (loose tolerance).
"""

import math

import pytest

from .test_streaming_sma_parity import _bars_to_frame, _make_deterministic_bars

# Windowed-default representatives — one per handler family
_WINDOWED_DEFAULT_REPS = [
    "bearish_fvg",
    "demand_zone_score",
    "roll_spread",
    "awesome_oscillator",
    "poc_rejection",
    "hurst_exponent",
]


class TestWindowedDefaultParity:
    """Scenario 8b: Windowed-default indicators match batch."""

    @pytest.mark.parametrize("indicator", _WINDOWED_DEFAULT_REPS)
    def test_windowed_default_matches_batch(self, indicator):
        """Construction succeeds and latest value ≈ batch last-row."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        # Use enough bars to satisfy min_lookback (hurst_exponent needs 100)
        bars = _make_deterministic_bars(250, seed=8)
        batch_last = (
            PandasTaIndicatorCalculator()
            .calculate(_bars_to_frame(bars), [indicator])
            .iloc[-1]
            .to_dict()
        )

        # Should not raise
        engine = StreamingIndicatorEngine(indicators=[indicator])
        for b in bars:
            engine.update(b)

        got = engine.latest().values.get(indicator, float("nan"))
        expected = batch_last.get(indicator, float("nan"))

        # Skip NaN↔NaN
        if math.isnan(got) and math.isnan(expected):
            return

        assert math.isclose(
            got, expected, rel_tol=1e-7, abs_tol=1e-9
        ), (
            f"{indicator}: streaming={got}, batch={expected}, "
            f"diff={abs(got - expected)}"
        )

    def test_unknown_name_still_raises(self):
        """A genuinely unknown name raises at construction."""
        from finbar_strategy_runtime.indicators._streaming_classifier import (
            UnsupportedStreamingIndicatorError,
        )
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        with pytest.raises(UnsupportedStreamingIndicatorError):
            StreamingIndicatorEngine(indicators=["typo_metric"])

    def test_windowed_default_engine_construction(self):
        """Engine construction with mixed streaming + windowed-default works."""
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        engine = StreamingIndicatorEngine(
            indicators=["sma_20", "bearish_fvg", "rsi_14"]
        )
        assert engine is not None

    def test_hurst_min_lookback_respected(self):
        """hurst_exponent has min_lookback=100; parity holds at 250 bars."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        indicator = "hurst_exponent"
        bars = _make_deterministic_bars(250, seed=42)
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

        assert math.isclose(
            got, expected, rel_tol=1e-7, abs_tol=1e-9
        ), (
            f"{indicator}: streaming={got}, batch={expected}, "
            f"diff={abs(got - expected)}"
        )


class TestSessionCountIndicatorWindow:
    """Session-count indicators (poc_slope_N) need a window covering N sessions.

    These group by calendar session and look back N sessions. A 50-bar
    window holds too few sessions at intraday timeframes, so the value
    miscomputes as 0.0. The engine resolves a larger window for them.
    """

    def test_poc_slope_5_matches_batch_with_enough_sessions(self):
        """poc_slope_5 streaming == batch when >=6 sessions are in window."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        indicator = "poc_slope_5"
        bars = _make_deterministic_bars(500, seed=3)
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
        assert math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-12), (
            f"{indicator}: streaming={got}, batch={expected}"
        )
