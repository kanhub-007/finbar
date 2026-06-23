"""MacdState — MACD with shared sub-state, O(1) per bar.

Owns one EMA(12), one EMA(26), and one signal EMA(9). Serves
``macd``, ``macd_signal``, and ``macd_hist`` from a single internal
state. Matches ``pandas_ta.macd`` with default parameters.
"""

from __future__ import annotations

from math import isnan

from finbar_strategy_runtime.indicators.streaming.ema_state import EmaState
from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)


class MacdState(StreamingIndicatorState):
    """Streaming state for ``macd``, ``macd_signal``, ``macd_hist``.

    Single source of truth: one ``EmaState(12)`` for the fast EMA, one
    ``EmaState(26)`` for the slow EMA, and one ``EmaState(9)`` for the
    signal line. All three outputs derive from this shared state.
    """

    def __init__(self) -> None:
        self._fast = EmaState(12)
        self._slow = EmaState(26)
        self._signal = EmaState(9)
        self._macd: float = float("nan")
        self._signal_val: float = float("nan")

    def update(self, bar: dict) -> float:
        """Ingest one bar; returns NaN (multi-output — use properties).

        Args:
            bar: Dict with key ``"close"``.

        Returns:
            Always NaN. Use ``.macd``, ``.signal``, ``.hist``.
        """
        fast_val = self._fast.update(bar)
        slow_val = self._slow.update(bar)

        if isnan(fast_val) or isnan(slow_val):
            return float("nan")

        self._macd = fast_val - slow_val
        self._signal_val = self._signal.update({"close": self._macd})

        return float("nan")  # multi-output

    def reset(self) -> None:
        """Clear accumulated state."""
        self._fast.reset()
        self._slow.reset()
        self._signal.reset()
        self._macd = float("nan")
        self._signal_val = float("nan")

    @property
    def macd(self) -> float:
        """MACD line = EMA(12) − EMA(26)."""
        return self._macd

    @property
    def signal(self) -> float:
        """Signal line = EMA(9) of MACD."""
        return self._signal_val

    @property
    def hist(self) -> float:
        """MACD histogram = MACD − Signal."""
        if isnan(self._macd) or isnan(self._signal_val):
            return float("nan")
        return self._macd - self._signal_val
