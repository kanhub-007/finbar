"""EmaState — incremental Exponential Moving Average with O(1) per-bar cost.

Seed initialisation matches ``pandas_ta.ema`` (``presma=True``): the EMA
is seeded with the SMA of the first ``length`` closes, then
``ema = α·x + (1−α)·ema`` where ``α = 2/(length+1)``.
"""

from __future__ import annotations

from collections import deque

from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)


class EmaState(StreamingIndicatorState):
    """Streaming state for ``ema_N`` indicators.

    Seeds with SMA over the first ``length`` bars (matching
    ``pandas_ta.ema`` with ``presma=True``), then applies the
    recursive EMA update.
    """

    def __init__(self, period: int) -> None:
        """Initialise with the EMA period.

        Args:
            period: Number of bars (the EMA smoothing constant will be
                ``α = 2/(period+1)``).
        """
        self._period: int = max(2, period)
        self._alpha: float = 2.0 / (self._period + 1.0)
        self._ema: float = float("nan")

        # Seed buffer for initial SMA
        self._seed_buffer: deque[float] = deque(maxlen=self._period)
        self._seed_sum: float = 0.0
        self._seeded: bool = False

    def update(self, bar: dict) -> float:
        """Ingest one bar; return the current EMA value or NaN.

        Args:
            bar: Dict with key ``"close"``.

        Returns:
            Current EMA value, or ``NaN`` until ``length`` bars seen.
        """
        close = float(bar["close"])

        if not self._seeded:
            self._seed_buffer.append(close)
            self._seed_sum += close
            if len(self._seed_buffer) == self._period:
                self._ema = self._seed_sum / self._period
                self._seeded = True
                return self._ema
            return float("nan")

        self._ema = self._alpha * close + (1.0 - self._alpha) * self._ema
        return self._ema

    def reset(self) -> None:
        """Clear accumulated state."""
        self._seed_buffer.clear()
        self._seed_sum = 0.0
        self._ema = float("nan")
        self._seeded = False

    @property
    def value(self) -> float:
        """Current EMA value, or NaN if not yet seeded."""
        return self._ema
