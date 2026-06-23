"""BbState — Bollinger Bands with O(1) per-bar rolling mean + variance.

Maintains a bounded deque of closes with running sum and sum-of-squares.
Serves ``bb_upper``, ``bb_middle``, ``bb_lower`` from a single state.
"""

from __future__ import annotations

from collections import deque
from math import isnan, sqrt

from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)


class BbState(StreamingIndicatorState):
    """Streaming state for ``bb_upper``, ``bb_middle``, ``bb_lower``.

    Maintains a bounded deque of closes and online mean/variance via
    running sums. Standard deviation multiplier = 2 (matching
    ``pandas_ta.bbands`` default).
    """

    def __init__(self, period: int = 20, nbdev: float = 2.0) -> None:
        """Initialise with the Bollinger Band period.

        Args:
            period: Rolling window length (default 20).
            nbdev: Standard deviation multiplier (default 2).
        """
        self._period: int = max(2, period)
        self._nbdev: float = nbdev
        self._buffer: deque[float] = deque(maxlen=self._period)
        self._sum: float = 0.0
        self._sum_sq: float = 0.0

    def update(self, bar: dict) -> float:
        """Ingest one bar; returns NaN (multi-output — use properties).

        Args:
            bar: Dict with key ``"close"``.

        Returns:
            Always NaN. Use ``.upper``, ``.middle``, ``.lower`` properties.
        """
        close = float(bar["close"])

        if len(self._buffer) == self._buffer.maxlen:
            old = self._buffer[0]
            self._sum -= old
            self._sum_sq -= old * old

        self._buffer.append(close)
        self._sum += close
        self._sum_sq += close * close

        return float("nan")  # multi-output — use properties

    def reset(self) -> None:
        """Clear accumulated state."""
        self._buffer.clear()
        self._sum = 0.0
        self._sum_sq = 0.0

    @property
    def middle(self) -> float:
        """Bollinger Band middle line (SMA)."""
        if len(self._buffer) < self._period:
            return float("nan")
        return self._sum / len(self._buffer)

    @property
    def upper(self) -> float:
        """Bollinger Band upper line (SMA + nbdev * σ)."""
        if len(self._buffer) < self._period:
            return float("nan")
        std = self._std
        if isnan(std) or std == 0.0:
            return self.middle
        return self.middle + self._nbdev * std

    @property
    def lower(self) -> float:
        """Bollinger Band lower line (SMA − nbdev * σ)."""
        if len(self._buffer) < self._period:
            return float("nan")
        std = self._std
        if isnan(std) or std == 0.0:
            return self.middle
        return self.middle - self._nbdev * std

    @property
    def _std(self) -> float:
        """Sample standard deviation (ddof=1, matching pandas_ta default)."""
        n = len(self._buffer)
        if n < 2:
            return 0.0
        mean = self._sum / n
        variance = (self._sum_sq / n) - (mean * mean)
        if variance < 0.0:
            variance = 0.0
        # Convert population variance to sample variance (ddof=1)
        if n > 1:
            variance = variance * n / (n - 1)
        return sqrt(variance)
