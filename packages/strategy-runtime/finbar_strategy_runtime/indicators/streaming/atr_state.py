"""AtrState — incremental Average True Range with Wilder smoothing, O(1) cost.

Matches ``pandas_ta.atr`` exactly: buffers the first ``length`` True Range
values, seeds with their SMA, then applies Wilder smoothing.
"""

from __future__ import annotations

from collections import deque
from math import isnan

from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)


class AtrState(StreamingIndicatorState):
    """Streaming state for the ``atr`` indicator.

    Matches ``pandas_ta.atr``: collects ``period`` TR values for an SMA
    seed, then applies Wilder smoothing (``α = 1/period``).
    """

    def __init__(self, period: int = 14) -> None:
        """Initialise with the ATR period.

        Args:
            period: Number of bars for the Wilder smoothing window
                (default 14).
        """
        self._period: int = max(1, period)
        self._alpha: float = 1.0 / self._period

        self._prev_close: float = float("nan")
        self._atr: float = float("nan")

        # Seed buffer for initial SMA
        self._seed_trs: deque[float] = deque(maxlen=self._period)
        self._seeded: bool = False

    def update(self, bar: dict) -> float:
        """Ingest one bar; return the current ATR value or NaN.

        Args:
            bar: Dict with keys ``"high"``, ``"low"``, ``"close"``.

        Returns:
            Current ATR value, or ``NaN`` until ``period`` bars seen.
        """
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])

        if isnan(self._prev_close):
            # First bar: TR = high - low (no prev_close to compare)
            tr = high - low
            self._prev_close = close
            self._seed_trs.append(tr)
            return float("nan")

        tr = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
        self._prev_close = close

        if not self._seeded:
            self._seed_trs.append(tr)
            if len(self._seed_trs) == self._period:
                self._atr = sum(self._seed_trs) / self._period
                self._seeded = True
                return self._atr
            return float("nan")

        self._atr = self._alpha * tr + (1.0 - self._alpha) * self._atr
        return self._atr

    def reset(self) -> None:
        """Clear accumulated state."""
        self._prev_close = float("nan")
        self._atr = float("nan")
        self._seed_trs.clear()
        self._seeded = False

    @property
    def value(self) -> float:
        """Current ATR value, or NaN if not yet seeded."""
        return self._atr
