"""AdxState — Average Directional Index, O(1) per bar.

Matches ``pandas_ta.adx``: Wilder-smoothed +DM/−DM/TR → DI+/DI− → DX → ADX.
Seeds smoothed values with SMA of first ``length`` values.
"""

from __future__ import annotations

from collections import deque
from math import isnan

from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)


class AdxState(StreamingIndicatorState):
    """Streaming state for the ``adx`` indicator (and associated DI lines)."""

    def __init__(self, period: int = 14) -> None:
        """Initialise with the ADX period.

        Args:
            period: Wilder smoothing length (default 14).
        """
        self._period: int = max(2, period)
        self._alpha: float = 1.0 / self._period

        self._prev_high: float = float("nan")
        self._prev_low: float = float("nan")
        self._prev_close: float = float("nan")

        # Smoothed values
        self._sm_dmp: float = float("nan")  # +DM
        self._sm_dmm: float = float("nan")  # −DM
        self._sm_tr: float = float("nan")   # TR
        self._adx: float = float("nan")

        # Seed buffers
        self._seed_dmp: deque[float] = deque(maxlen=self._period)
        self._seed_dmm: deque[float] = deque(maxlen=self._period)
        self._seed_tr: deque[float] = deque(maxlen=self._period)
        self._seeded: bool = False
        self._dx_values: deque[float] = deque(maxlen=self._period)

    def update(self, bar: dict) -> float:
        """Ingest one bar; return the current ADX value or NaN.

        Args:
            bar: Dict with keys ``"high"``, ``"low"``, ``"close"``.

        Returns:
            Current ADX value, or NaN until ``2 * period`` bars seen.
        """
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])

        if isnan(self._prev_high):
            self._prev_high = high
            self._prev_low = low
            self._prev_close = close
            return float("nan")

        # Directional Movement
        up_move = high - self._prev_high
        down_move = self._prev_low - low

        dmp = up_move if (up_move > down_move and up_move > 0) else 0.0
        dmm = down_move if (down_move > up_move and down_move > 0) else 0.0

        # True Range
        tr = max(
            high - low,
            abs(high - self._prev_close),
            abs(low - self._prev_close),
        )

        self._prev_high = high
        self._prev_low = low
        self._prev_close = close

        if not self._seeded:
            self._seed_dmp.append(dmp)
            self._seed_dmm.append(dmm)
            self._seed_tr.append(tr)
            if len(self._seed_dmp) == self._period:
                self._sm_dmp = sum(self._seed_dmp) / self._period
                self._sm_dmm = sum(self._seed_dmm) / self._period
                self._sm_tr = sum(self._seed_tr) / self._period
                self._seeded = True
                # Compute first DX and seed ADX
                return self._update_adx()
            return float("nan")

        # Wilder smoothing of DM and TR
        self._sm_dmp = self._alpha * dmp + (1.0 - self._alpha) * self._sm_dmp
        self._sm_dmm = self._alpha * dmm + (1.0 - self._alpha) * self._sm_dmm
        self._sm_tr = self._alpha * tr + (1.0 - self._alpha) * self._sm_tr

        return self._update_adx()

    def _update_adx(self) -> float:
        """Compute DX from current smoothed values and update ADX."""
        if self._sm_tr == 0.0:
            di_p = 0.0
            di_m = 0.0
        else:
            di_p = 100.0 * self._sm_dmp / self._sm_tr
            di_m = 100.0 * self._sm_dmm / self._sm_tr

        di_sum = di_p + di_m
        if di_sum == 0.0:
            dx = 0.0
        else:
            dx = 100.0 * abs(di_p - di_m) / di_sum

        self._dx_values.append(dx)

        if isnan(self._adx):
            if len(self._dx_values) == self._period:
                self._adx = sum(self._dx_values) / self._period
            return float("nan")

        self._adx = self._alpha * dx + (1.0 - self._alpha) * self._adx
        return self._adx

    def reset(self) -> None:
        """Clear accumulated state."""
        self._prev_high = float("nan")
        self._prev_low = float("nan")
        self._prev_close = float("nan")
        self._sm_dmp = float("nan")
        self._sm_dmm = float("nan")
        self._sm_tr = float("nan")
        self._adx = float("nan")
        self._seed_dmp.clear()
        self._seed_dmm.clear()
        self._seed_tr.clear()
        self._dx_values.clear()
        self._seeded = False

    @property
    def value(self) -> float:
        """Current ADX value, or NaN if not yet warm."""
        return self._adx
