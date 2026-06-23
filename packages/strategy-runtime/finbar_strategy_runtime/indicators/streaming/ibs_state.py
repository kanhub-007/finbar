"""IbsState — Internal Bar Strength, O(1) from the bar itself.

``ibs = (close − low) / (high − low)``. No state needed — one-bar
calculation.
"""

from __future__ import annotations

from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)


class IbsState(StreamingIndicatorState):
    """Streaming state for the ``ibs`` indicator.

    Purely point-in-time: computed from the bar's own OHLC values.
    Returns NaN when high == low (no range).
    """

    def __init__(self) -> None:
        self._current: float = float("nan")

    def update(self, bar: dict) -> float:
        """Compute IBS from the current bar.

        Args:
            bar: Dict with keys ``"open"``, ``"high"``, ``"low"``, ``"close"``.

        Returns:
            IBS value in [0, 1], or NaN if high == low.
        """
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])

        rng = high - low
        if rng == 0.0:
            self._current = float("nan")
            return float("nan")
        self._current = (close - low) / rng
        return self._current

    def reset(self) -> None:
        """No state to clear beyond current value."""
        self._current = float("nan")

    @property
    def value(self) -> float:
        """Most recently computed IBS value."""
        return self._current
