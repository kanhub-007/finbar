"""RvolState — Relative Volume, O(1) per bar.

``rvol = volume / SMA(volume, period=20)``. Maintains a rolling volume
SMA and divides the current bar's volume by it.
"""

from __future__ import annotations

from collections import deque

from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)


class RvolState(StreamingIndicatorState):
    """Streaming state for the ``rvol`` indicator.

    Maintains a rolling SMA of volume (default window = 20), then
    divides each bar's volume by that SMA. Returns NaN until the
    rolling window is full.
    """

    def __init__(self, period: int = 20) -> None:
        """Initialise with the rolling volume period.

        Args:
            period: Window size for the volume SMA (default 20).
        """
        self._period: int = max(1, period)
        self._vol_buffer: deque[float] = deque(maxlen=self._period)
        self._vol_sum: float = 0.0

    def update(self, bar: dict) -> float:
        """Ingest one bar; return the current RVOL value or NaN.

        Args:
            bar: Dict with key ``"volume"``.

        Returns:
            Current RVOL value, or NaN until ``period`` bars seen.
        """
        volume = float(bar["volume"])

        if len(self._vol_buffer) == self._vol_buffer.maxlen:
            old = self._vol_buffer[0]
            self._vol_sum -= old

        self._vol_buffer.append(volume)
        self._vol_sum += volume

        if len(self._vol_buffer) < self._period:
            return float("nan")

        avg = self._vol_sum / len(self._vol_buffer)
        if avg == 0.0:
            return float("nan")
        return volume / avg

    def reset(self) -> None:
        """Clear accumulated state."""
        self._vol_buffer.clear()
        self._vol_sum = 0.0

    @property
    def value(self) -> float:
        """Current RVOL value, or NaN if not yet warm."""
        if len(self._vol_buffer) < self._period:
            return float("nan")
        avg = self._vol_sum / len(self._vol_buffer)
        if avg == 0.0:
            return float("nan")
        return self._vol_buffer[-1] / avg
