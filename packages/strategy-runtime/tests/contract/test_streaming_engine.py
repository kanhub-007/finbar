"""Contract tests for Scenarios 4, 5, 6: engine API, warmup, and reset.

Scenario 4: update returns latest row, bounded memory.
Scenario 5: warmup semantics match batch MIN_BARS.
Scenario 6: reset clears all per-indicator state.
"""

import math

from .test_streaming_sma_parity import _make_deterministic_bars


class TestStreamingEngineApi:
    """Scenario 4: update/latest API and bounded memory."""

    def test_update_returns_latest_row(self):
        """Each update returns the latest row dict."""
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        indicators = ["sma_20", "ema_26", "rsi_14"]
        engine = StreamingIndicatorEngine(indicators=indicators)
        bars = _make_deterministic_bars(60, seed=2)

        latest = None
        for b in bars:
            latest = engine.update(b)

        assert latest is not None
        assert "rsi_14" in latest.values

    def test_latest_before_any_update_returns_empty(self):
        """latest() without any update() returns an empty LatestBar."""
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        engine = StreamingIndicatorEngine(indicators=["sma_20"])
        bar = engine.latest()
        assert bar.values == {}
        assert bar.is_ready is False
        assert bar.bars_seen == 0

    def test_bounded_memory_growth(self):
        """Memory growth is bounded (not proportional to n)."""
        import tracemalloc

        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        indicators = ["sma_20", "ema_26", "rsi_14", "atr", "ibs"]
        engine = StreamingIndicatorEngine(indicators=indicators)

        # Warm up
        warmup = _make_deterministic_bars(60, seed=2)
        for b in warmup:
            engine.update(b)

        tracemalloc.start()
        before = tracemalloc.get_traced_memory()[0]

        # Feed many more bars
        extra = _make_deterministic_bars(10_000, seed=99)
        for b in extra:
            engine.update(b)

        after = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()

        growth = after - before
        assert growth < 5_000_000, (
            f"Memory grew by {growth} bytes over 10k bars — exceeds 5 MB budget"
        )


class TestStreamingEngineWarmup:
    """Scenario 5: warmup semantics match batch MIN_BARS."""

    def test_not_ready_before_min_bars(self):
        """is_ready() is False before MIN_BARS bars."""
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        engine = StreamingIndicatorEngine(indicators=["sma_20"])
        bars = _make_deterministic_bars(10, seed=5)

        for b in bars[:-1]:  # 9 bars < MIN_BARS=10
            engine.update(b)
        assert not engine.is_ready()

    def test_ready_at_min_bars(self):
        """is_ready() is True once MIN_BARS bars ingested."""
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        engine = StreamingIndicatorEngine(indicators=["sma_20"])
        bars = _make_deterministic_bars(10, seed=5)

        for b in bars:  # exactly 10 bars
            engine.update(b)
        assert engine.is_ready()


class TestStreamingEngineReset:
    """Scenario 6: reset clears all per-indicator state."""

    def test_reset_reproduces_identical_values(self):
        """After reset, re-ingesting the same bars reproduces identical values."""
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        bars = _make_deterministic_bars(80, seed=4)
        engine = StreamingIndicatorEngine(indicators=["ema_26", "rsi_14"])
        for b in bars:
            engine.update(b)
        first = dict(engine.latest().values)

        engine.reset()
        assert not engine.is_ready()

        for b in bars:
            engine.update(b)
        second = engine.latest().values

        for name in ("ema_26", "rsi_14"):
            v1 = first.get(name, float("nan"))
            v2 = second.get(name, float("nan"))
            if math.isnan(v1) and math.isnan(v2):
                continue
            assert math.isclose(v2, v1, rel_tol=1e-12, abs_tol=1e-15), (
                f"{name}: first={v1}, second={v2} after reset"
            )
