"""RsiState — incremental RSI with Wilder smoothing, O(1) per-bar cost.

Matches ``pandas_ta.rsi`` exactly: seeds avg-gain and avg-loss with the
first bar's change (like ``pandas.ewm``), then applies Wilder smoothing.
"""

from __future__ import annotations

from math import isnan


class RsiState:
    """Streaming state for ``rsi_N`` indicators.

    Uses Wilder smoothing of average gain and average loss. The first
    change after the initial bar seeds both averages. This matches
    ``pandas_ta.rsi`` which internally uses ``ewm(alpha=1/length)``.
    """

    def __init__(self, period: int) -> None:
        """Initialise with the RSI period.

        Args:
            period: Number of bars for the Wilder smoothing window.
        """
        self._period: int = max(2, period)
        self._alpha: float = 1.0 / self._period

        self._prev_close: float = float("nan")
        self._avg_gain: float = float("nan")
        self._avg_loss: float = float("nan")

    def update(self, bar: dict) -> float:
        """Ingest one bar; return the current RSI value or NaN.

        Args:
            bar: Dict with key ``"close"``.

        Returns:
            Current RSI value (0–100), or ``NaN`` if fewer than
            ``period + 1`` bars have been seen.
        """
        close = float(bar["close"])

        if isnan(self._prev_close):
            self._prev_close = close
            return float("nan")

        change = close - self._prev_close
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        self._prev_close = close

        if isnan(self._avg_gain):
            # Seed: first change sets both averages (matches ewm behaviour)
            self._avg_gain = gain
            self._avg_loss = loss
        else:
            self._avg_gain = self._alpha * gain + (1.0 - self._alpha) * self._avg_gain
            self._avg_loss = self._alpha * loss + (1.0 - self._alpha) * self._avg_loss

        if self._avg_loss == 0.0:
            return 100.0

        rs = self._avg_gain / self._avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def reset(self) -> None:
        """Clear accumulated state."""
        self._prev_close = float("nan")
        self._avg_gain = float("nan")
        self._avg_loss = float("nan")

    @property
    def value(self) -> float:
        """Current RSI value, or NaN if not yet seeded."""
        if isnan(self._avg_gain):
            return float("nan")
        if self._avg_loss == 0.0:
            return 100.0
        rs = self._avg_gain / self._avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
