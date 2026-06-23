"""KamaState — Kaufman Adaptive Moving Average, O(1) per bar.

KAMA = prev_kama + sc * (close - prev_kama)
where sc = (ER * (fast_sc - slow_sc) + slow_sc)^2
and ER = Kaufman Efficiency Ratio.
Matches ``pandas_ta.kama``.
"""

from __future__ import annotations

from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)

from math import isnan

from finbar_strategy_runtime.indicators.streaming.ker_state import KerState


class KamaState(StreamingIndicatorState):
    """Streaming state for the ``kama`` indicator.

    Uses an internal ``KerState`` for the efficiency ratio, then applies
    the adaptive smoothing constant.
    """

    def __init__(
        self,
        period: int = 10,
        fast_period: int = 2,
        slow_period: int = 30,
    ) -> None:
        """Initialise KAMA.

        Args:
            period: ER lookback (default 10).
            fast_period: Fast EMA constant (default 2).
            slow_period: Slow EMA constant (default 30).
        """
        self._ker = KerState(period)
        self._fast_sc: float = 2.0 / (fast_period + 1.0)
        self._slow_sc: float = 2.0 / (slow_period + 1.0)
        self._kama: float = float("nan")

    def update(self, bar: dict) -> float:
        """Ingest one bar; return the current KAMA value or NaN.

        Args:
            bar: Dict with key ``"close"``.

        Returns:
            Current KAMA value, or NaN until warm.
        """
        close = float(bar["close"])
        er = self._ker.update(bar)

        if isnan(er):
            return float("nan")

        sc = (er * (self._fast_sc - self._slow_sc) + self._slow_sc) ** 2

        if isnan(self._kama):
            self._kama = close
            return close

        self._kama = self._kama + sc * (close - self._kama)
        return self._kama

    def reset(self) -> None:
        """Clear accumulated state."""
        self._ker.reset()
        self._kama = float("nan")

    @property
    def value(self) -> float:
        """Current KAMA value, or NaN if not yet warm."""
        return self._kama
