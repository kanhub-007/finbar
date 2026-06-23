"""VwapState — session-cumulative Volume-Weighted Average Price, O(1) per bar.

Matches ``pandas_ta.vwap``: cumulative (PV) / V over a session.
Resets on session boundary (calendar date change).
"""

from __future__ import annotations

from finbar_strategy_runtime.indicators._bar_timestamp import parse_bar_timestamps
from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)


class VwapState(StreamingIndicatorState):
    """Streaming state for the ``vwap`` indicator.

    Maintains cumulative price×volume and volume. Resets when the
    calendar date changes (if ``timestamp`` is in the bar dict).
    """

    def __init__(self) -> None:
        self._cum_pv: float = 0.0
        self._cum_vol: float = 0.0
        self._last_date: str | None = None

    def update(self, bar: dict) -> float:
        """Ingest one bar; return the current VWAP value or NaN.

        Args:
            bar: Dict with keys ``"high"``, ``"low"``, ``"close"``, ``"volume"``,
                and optionally ``"timestamp"`` for session detection.

        Returns:
            Current VWAP value, or NaN if cumulative volume is zero.
        """
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        volume = float(bar["volume"])

        # VWAP uses typical price: (high + low + close) / 3
        typical_price = (high + low + close) / 3.0

        # Session boundary detection.
        ts = bar.get("timestamp")
        if ts is not None:
            bar_date = _bar_date(ts)
            if self._last_date is not None and bar_date != self._last_date:
                self._cum_pv = 0.0
                self._cum_vol = 0.0
            self._last_date = bar_date

        if volume <= 0:
            if self._cum_vol == 0.0:
                return float("nan")
            return self._cum_pv / self._cum_vol

        self._cum_pv += typical_price * volume
        self._cum_vol += volume

        if self._cum_vol == 0.0:
            return float("nan")
        return self._cum_pv / self._cum_vol

    def reset(self) -> None:
        """Clear accumulated state."""
        self._cum_pv = 0.0
        self._cum_vol = 0.0
        self._last_date = None

    @property
    def value(self) -> float:
        """Current VWAP value, or NaN if no volume accumulated."""
        if self._cum_vol == 0.0:
            return float("nan")
        return self._cum_pv / self._cum_vol


def _bar_date(timestamp) -> str:
    """Return the UTC calendar date for a bar timestamp."""
    return parse_bar_timestamps([timestamp])[0].date().isoformat()
