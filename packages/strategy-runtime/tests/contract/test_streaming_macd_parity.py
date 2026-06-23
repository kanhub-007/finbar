"""Contract tests for Scenario 3: MACD shared sub-state parity.

Verifies that MacdState serves macd, macd_signal, macd_hist from a single
internal state, and that requesting only macd_signal yields the same value
(single source of truth).
"""

import math

from .test_streaming_sma_parity import _bars_to_frame, _make_deterministic_bars


class TestStreamingMacdParity:
    """Scenario 3: MACD parity with shared sub-state."""

    def test_all_three_outputs_parity(self):
        """macd, macd_signal, macd_hist all equal batch last-row."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        indicators = ["macd", "macd_signal", "macd_hist"]
        bars = _make_deterministic_bars(100, seed=3)
        batch_last = (
            PandasTaIndicatorCalculator()
            .calculate(_bars_to_frame(bars), indicators)
            .iloc[-1]
            .to_dict()
        )

        engine = StreamingIndicatorEngine(indicators=indicators)
        for b in bars:
            engine.update(b)
        got = engine.latest().values

        for name in indicators:
            batch_val = batch_last[name]
            stream_val = got.get(name, float("nan"))
            if math.isnan(batch_val) and math.isnan(stream_val):
                continue
            assert math.isclose(
                stream_val, batch_val, rel_tol=1e-9, abs_tol=1e-12
            ), (
                f"{name}: streaming={stream_val}, batch={batch_val}, "
                f"diff={abs(stream_val - batch_val)}"
            )

    def test_single_source_of_truth(self):
        """Requesting only macd_signal yields identical value."""
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        bars = _make_deterministic_bars(100, seed=3)

        # Full set
        engine_full = StreamingIndicatorEngine(
            indicators=["macd", "macd_signal", "macd_hist"]
        )
        for b in bars:
            engine_full.update(b)
        full_signal = engine_full.latest().values.get("macd_signal", float("nan"))

        # Only signal
        engine_signal = StreamingIndicatorEngine(indicators=["macd_signal"])
        for b in bars:
            engine_signal.update(b)
        signal_only = engine_signal.latest().values.get("macd_signal", float("nan"))

        assert math.isclose(
            signal_only, full_signal, rel_tol=1e-9, abs_tol=1e-12
        ), (
            f"macd_signal single-source violation: full={full_signal}, "
            f"signal-only={signal_only}"
        )
