"""SmaState — incremental Simple Moving Average with O(1) per-bar cost.

Uses a ``deque(maxlen=length)`` and running sum. The first non-NaN value
equals the mean of the first ``length`` closes, matching ``pandas_ta.sma``.
"""

from __future__ import annotations

from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)

from collections import deque
from math import isnan


class SmaState(StreamingIndicatorState):
    """Streaming state for ``sma_N`` indicators.

    Maintains a bounded deque of the last ``length`` closes and a
    running sum. ``update(bar)`` returns ``NaN`` until ``length``
    bars have been ingested, then returns the arithmetic mean.
    """

    def __init__(self, period: int) -> None:
        """Initialise with the SMA period.

        Args:
            period: Number of bars for the moving average window.
        """
        self._period: int = max(1, period)
        self._buffer: deque[float] = deque(maxlen=self._period)
        self._running_sum: float = 0.0

    def update(self, bar: dict) -> float:
        """Ingest one bar; return the current SMA value or NaN.

        Args:
            bar: Dict with key ``"close"``.

        Returns:
            Current SMA value, or ``NaN`` if fewer than ``period``
            bars have been seen.
        """
        close = float(bar["close"])

        if len(self._buffer) == self._buffer.maxlen:
            old = self._buffer[0]
            self._running_sum -= old

        self._buffer.append(close)
        self._running_sum += close

        if len(self._buffer) < self._period:
            return float("nan")

        return self._running_sum / len(self._buffer)

    def reset(self) -> None:
        """Clear accumulated state."""
        self._buffer.clear()
        self._running_sum = 0.0

    @property
    def value(self) -> float:
        """Current SMA value, or NaN if not yet warm."""
        if len(self._buffer) < self._period:
            return float("nan")
        return self._running_sum / len(self._buffer)
