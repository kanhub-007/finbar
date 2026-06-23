"""KerState — Kaufman Efficiency Ratio, rolling O(1).

KER = abs(close − close[−period]) / sum(abs(change_i)) over ``period``.
Matches ``pandas_ta.er`` (Efficiency Ratio).
"""

from __future__ import annotations

from collections import deque
from math import isnan

from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)


class KerState(StreamingIndicatorState):
    """Streaming state for the ``ker`` (Kaufman Efficiency Ratio) indicator."""

    def __init__(self, period: int = 10) -> None:
        """Initialise with the KER period.

        Args:
            period: Lookback window (default 10).
        """
        self._period: int = max(2, period)
        self._closes: deque[float] = deque(maxlen=self._period + 1)
        self._abs_changes: deque[float] = deque(maxlen=self._period)
        self._abs_changes_sum: float = 0.0
        self._prev_close: float = float("nan")

    def update(self, bar: dict) -> float:
        """Ingest one bar; return the current KER value or NaN.

        Args:
            bar: Dict with key ``"close"``.

        Returns:
            Current KER value (0–1), or NaN until ``period + 1`` bars seen.
        """
        close = float(bar["close"])

        if isnan(self._prev_close):
            self._prev_close = close
            self._closes.append(close)
            return float("nan")

        abs_change = abs(close - self._prev_close)
        self._prev_close = close

        if len(self._abs_changes) == self._abs_changes.maxlen:
            old_change = self._abs_changes[0]
            self._abs_changes_sum -= old_change

        self._abs_changes.append(abs_change)
        self._abs_changes_sum += abs_change

        self._closes.append(close)

        if len(self._closes) < self._period + 1:
            return float("nan")

        numerator = abs(self._closes[-1] - self._closes[0])
        if self._abs_changes_sum == 0.0:
            return 0.0 if numerator == 0.0 else float("nan")

        return numerator / self._abs_changes_sum

    def reset(self) -> None:
        """Clear accumulated state."""
        self._closes.clear()
        self._abs_changes.clear()
        self._abs_changes_sum = 0.0
        self._prev_close = float("nan")

    @property
    def value(self) -> float:
        """Current KER value, or NaN if not yet warm."""
        if len(self._closes) < self._period + 1:
            return float("nan")
        numerator = abs(self._closes[-1] - self._closes[0])
        if self._abs_changes_sum == 0.0:
            return 0.0 if numerator == 0.0 else float("nan")
        return numerator / self._abs_changes_sum
