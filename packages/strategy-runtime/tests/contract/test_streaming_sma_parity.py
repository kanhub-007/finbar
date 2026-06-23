"""Contract tests for Scenario 1: Streaming SMA equals batch last-row value.

Verifies parity between IncrementalIndicatorEngine and the batch
PandasTaIndicatorCalculator for SMA at various periods.
"""

import math

# ── helpers (will move to conftest once stable) ─────────────────────────────
import numpy as np
import pandas as pd
import pytest

# Fixed int-second origin (2024-07-01 00:00:00 UTC) with 1-hour spacing.
# Real timestamps are required so session/date-sensitive indicators
# (vp_*, mp_*, AMT) compute against real calendar dates instead of a
# fabricated index. Non-session indicators ignore the field.
_BAR_ORIGIN_TS = 1719792000
_BAR_SPACING_S = 3600


def _make_deterministic_bars(length: int, seed: int = 1) -> list[dict]:
    """Generate deterministic OHLCV bars as list of dicts.

    Each bar carries a real int-second ``timestamp`` (1 hour apart) so
    session-sensitive indicators can be exercised correctly.
    """
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1.5, length))
    high = np.maximum(close + np.abs(rng.normal(0, 1, length)), close)
    low = np.minimum(close - np.abs(rng.normal(0, 1, length)), close)
    open_ = (close + rng.normal(0, 0.5, length))
    volume = rng.integers(100000, 1000000, length)

    bars: list[dict] = []
    for i in range(length):
        bars.append(
            {
                "timestamp": _BAR_ORIGIN_TS + i * _BAR_SPACING_S,
                "open": float(open_[i]),
                "high": float(high[i]),
                "low": float(low[i]),
                "close": float(close[i]),
                "volume": float(volume[i]),
            }
        )
    return bars


def _bars_to_frame(bars: list[dict]) -> pd.DataFrame:
    """Convert list of bar dicts to a DataFrame with a datetime index.

    When every bar carries a ``timestamp`` field, it is used as the (UTC)
    index and dropped from the columns; otherwise a deterministic
    synthetic hourly index is fabricated.
    """
    if not bars:
        return pd.DataFrame()
    if all("timestamp" in b for b in bars):
        ts = [b["timestamp"] for b in bars]
        first = ts[0]
        if isinstance(first, (int, float)) and not isinstance(first, bool):
            unit = "ms" if abs(float(first)) >= 1e11 else "s"
            idx = pd.DatetimeIndex(pd.to_datetime(ts, unit=unit, utc=True))
        else:
            idx = pd.DatetimeIndex(pd.to_datetime(ts, utc=True))
        data = [{k: v for k, v in b.items() if k != "timestamp"} for b in bars]
        return pd.DataFrame(data, index=idx)
    dates = pd.date_range("2024-01-01", periods=len(bars), freq="h")
    return pd.DataFrame(bars, index=dates)


# ── tests ────────────────────────────────────────────────────────────────────


class TestStreamingSmaParity:
    """Scenario 1: Streaming SMA equals batch for various periods."""

    @pytest.mark.parametrize(
        "period,bar_count,seed",
        [
            (20, 50, 1),   # sma_20 over 50 bars
            (200, 250, 2),  # sma_200 at minimum-usable boundary
            (37, 50, 3),    # dynamic period sma_37
            (10, 30, 4),    # sma_10 over 30 bars
            (50, 100, 5),   # sma_50 over 100 bars
        ],
    )
    def test_sma_parity(self, period, bar_count, seed):
        """Streaming sma_N latest value equals batch last-row value."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        name = f"sma_{period}"
        bars = _make_deterministic_bars(bar_count, seed=seed)

        # Batch reference
        batch_calc = PandasTaIndicatorCalculator()
        batch_last = (
            batch_calc.calculate(_bars_to_frame(bars), [name])
            .iloc[-1]
            .to_dict()
        )

        # Streaming engine
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        engine = StreamingIndicatorEngine(indicators=[name])
        for b in bars:
            engine.update(b)
        streaming_last = engine.latest().values

        batch_val = batch_last[name]
        stream_val = streaming_last.get(name, float("nan"))

        # NaN ↔ NaN is acceptable (warmup window not complete)
        if math.isnan(batch_val) and math.isnan(stream_val):
            return

        assert math.isclose(
            stream_val,
            batch_val,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ), (
            f"{name}: streaming={stream_val}, batch={batch_val}, "
            f"diff={abs(stream_val - batch_val)}"
        )

    def test_sma_returns_nan_before_period_bars(self):
        """SMA returns NaN when bars seen < period, matching batch behaviour."""
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        name = "sma_20"
        bars = _make_deterministic_bars(15, seed=10)  # < 20 bars

        engine = StreamingIndicatorEngine(indicators=[name])
        for b in bars:
            engine.update(b)

        latest = engine.latest()
        # Before MIN_BARS (10) the engine may not be ready;
        # after MIN_BARS but before period, sma_20 should be NaN
        val = latest.values.get(name, float("nan"))
        assert math.isnan(val) or val is None, (
            f"sma_20 with 15 bars should be NaN/absent, got {val}"
        )
