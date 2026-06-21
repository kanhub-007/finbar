"""Contract tests for Scenario 2: Streaming EMA, RSI, ATR equal batch.

Verifies parity for recursive/stochastic indicators that use seed-based
initialisation (EMA seed=SMA of first length, RSI Wilder smoothing,
ATR Wilder TR smoothing). Also tests numerical stability over long streams.
"""

import math

import numpy as np
import pytest

from .test_streaming_sma_parity import (
    _BAR_SPACING_S,
    _bars_to_frame,
    _make_deterministic_bars,
)


class TestStreamingEmaParity:
    """Scenario 2: EMA parity."""

    @pytest.mark.parametrize(
        "period,bar_count,seed",
        [
            (26, 100, 7),
            (12, 100, 8),
            (21, 100, 9),  # dynamic ema_21
        ],
    )
    def test_ema_parity(self, period, bar_count, seed):
        """Streaming ema_N latest equals batch last-row."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        name = f"ema_{period}"
        bars = _make_deterministic_bars(bar_count, seed=seed)
        batch_last = (
            PandasTaIndicatorCalculator()
            .calculate(_bars_to_frame(bars), [name])
            .iloc[-1]
            .to_dict()
        )

        engine = StreamingIndicatorEngine(indicators=[name])
        for b in bars:
            engine.update(b)
        got = engine.latest().values.get(name, float("nan"))
        expected = batch_last[name]

        if math.isnan(got) and math.isnan(expected):
            return
        assert math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-12), (
            f"{name}: streaming={got}, batch={expected}, diff={abs(got - expected)}"
        )


class TestStreamingRsiParity:
    """Scenario 2: RSI parity."""

    @pytest.mark.parametrize(
        "period,bar_count,seed",
        [
            (14, 100, 7),
            (7, 100, 8),
            (21, 100, 9),  # dynamic rsi_21
        ],
    )
    def test_rsi_parity(self, period, bar_count, seed):
        """Streaming rsi_N latest equals batch last-row."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        name = f"rsi_{period}"
        bars = _make_deterministic_bars(bar_count, seed=seed)
        batch_last = (
            PandasTaIndicatorCalculator()
            .calculate(_bars_to_frame(bars), [name])
            .iloc[-1]
            .to_dict()
        )

        engine = StreamingIndicatorEngine(indicators=[name])
        for b in bars:
            engine.update(b)
        got = engine.latest().values.get(name, float("nan"))
        expected = batch_last[name]

        if math.isnan(got) and math.isnan(expected):
            return
        assert math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-12), (
            f"{name}: streaming={got}, batch={expected}, diff={abs(got - expected)}"
        )

    def test_rsi_no_drift_over_2000_bars(self):
        """RSI numerical stability: no drift beyond tolerance over 2000 bars."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        name = "rsi_14"
        bars = _make_deterministic_bars(2000, seed=42)
        batch_last = (
            PandasTaIndicatorCalculator()
            .calculate(_bars_to_frame(bars), [name])
            .iloc[-1]
            .to_dict()
        )

        engine = StreamingIndicatorEngine(indicators=[name])
        for b in bars:
            engine.update(b)
        got = engine.latest().values.get(name, float("nan"))
        expected = batch_last[name]

        assert math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-12), (
            f"RSI drifted after 2000 bars: streaming={got}, batch={expected}, "
            f"diff={abs(got - expected)}"
        )


class TestStreamingAtrParity:
    """Scenario 2: ATR parity."""

    @pytest.mark.parametrize(
        "period,bar_count,seed",
        [
            (14, 100, 7),
            (7, 100, 8),  # dynamic atr_7
        ],
    )
    def test_atr_parity(self, period, bar_count, seed):
        """Streaming atr_N latest equals batch last-row."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        name = "atr" if period == 14 else f"atr_{period}"
        bars = _make_deterministic_bars(bar_count, seed=seed)
        batch_last = (
            PandasTaIndicatorCalculator()
            .calculate(_bars_to_frame(bars), [name])
            .iloc[-1]
            .to_dict()
        )

        engine = StreamingIndicatorEngine(indicators=[name])
        for b in bars:
            engine.update(b)
        got = engine.latest().values.get(name, float("nan"))
        expected = batch_last[name]

        if math.isnan(got) and math.isnan(expected):
            return
        assert math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-12), (
            f"{name}: streaming={got}, batch={expected}, diff={abs(got - expected)}"
        )

    def test_atr_zero_range_does_not_go_nan(self):
        """ATR over bars with zero range (high == low) does not go NaN after warmup."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        name = "atr"
        # 50 warmup bars with normal range, then 50 flat bars
        warmup = _make_deterministic_bars(50, seed=1)
        flat = []
        last_close = warmup[-1]["close"]
        last_ts = warmup[-1]["timestamp"]
        for i in range(50):
            flat.append(
                {
                    "timestamp": last_ts + (i + 1) * _BAR_SPACING_S,
                    "open": last_close,
                    "high": last_close,
                    "low": last_close,
                    "close": last_close,
                    "volume": 100000.0,
                }
            )
        bars = warmup + flat

        batch_last = (
            PandasTaIndicatorCalculator()
            .calculate(_bars_to_frame(bars), [name])
            .iloc[-1]
            .to_dict()
        )

        engine = StreamingIndicatorEngine(indicators=[name])
        for b in bars:
            engine.update(b)
        got = engine.latest().values.get(name, float("nan"))
        expected = batch_last[name]

        assert not math.isnan(got), f"ATR went NaN after zero-range bars"
        assert math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-12), (
            f"ATR: streaming={got}, batch={expected}, diff={abs(got - expected)}"
        )


class TestStreamingEmaRsiAtrCombined:
    """Scenario 2 combined: EMA, RSI, ATR computed together."""

    def test_all_three_parity(self):
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        indicators = ["ema_26", "rsi_14", "atr"]
        bars = _make_deterministic_bars(100, seed=7)
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
