"""WindowedIndicatorState — bounded ring-buffer + recompute via batch handler.

Used for two classes of indicators:
- VP-prefix WINDOWED (e.g. ``rvp_poc_48``, ``vp_poc_10d``)
- Windowed-default (~183 indicators with registered handlers but no
  hand-written streaming state class).

Buffers bars in a ``deque(maxlen=window)`` and calls the registered
batch handler on the deque slice each update. Per-bar cost is O(window).
"""

from __future__ import annotations

from collections import deque
from math import isnan

import pandas as pd


class WindowedIndicatorState:
    """Bounded ring buffer that recomputes an indicator over the window.

    Stores at most ``maxlen`` bars. Each ``update()`` appends a bar,
    converts the deque to a DataFrame, calls the registered batch handler,
    and returns the latest-row value for the indicator.
    """

    # Cached at module level to avoid repeated imports in _compute
    _handlers = None

    def __init__(self, name: str, maxlen: int) -> None:
        """Initialise with the indicator name and window size.

        Args:
            name: Indicator name (e.g. ``"bearish_fvg"``).
            maxlen: Maximum number of bars to retain (window size).
        """
        self._name = name
        self._buffer: deque[dict] = deque(maxlen=max(maxlen, 1))
        self._current: float = float("nan")
        # Pre-compute a datetime index pattern for reuse
        self._index: pd.DatetimeIndex | None = None

    def update(self, bar: dict) -> float:
        """Ingest one bar; recompute indicator and return latest value.

        Args:
            bar: OHLCV bar dict.

        Returns:
            Latest indicator value, or NaN if window not full.
        """
        self._buffer.append(bar)

        # We need at least some bars. defer until buffer is non-trivial.
        if len(self._buffer) < 2:
            return float("nan")

        # Build DataFrame from buffer
        df = self._to_dataframe()
        if df.empty:
            return float("nan")

        # Call the registered batch handler
        val = self._compute(df)
        self._current = val
        return val

    def reset(self) -> None:
        """Clear accumulated state."""
        self._buffer.clear()
        self._current = float("nan")

    @property
    def value(self) -> float:
        """Most recently computed value."""
        return self._current

    # ── internal ────────────────────────────────────────────────────────

    def _to_dataframe(self) -> pd.DataFrame:
        """Convert the deque buffer to a DataFrame with a datetime index."""
        n = len(self._buffer)
        if self._index is None or len(self._index) < n:
            self._index = pd.date_range("2024-01-01", periods=n, freq="h")
        return pd.DataFrame(list(self._buffer), index=self._index[:n])

    def _compute(self, df: pd.DataFrame) -> float:
        """Recompute the indicator over the window slice."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            _INDICATOR_HANDLERS,
        )
        from finbar_strategy_runtime.indicators._dynamic_dispatch import (
            _is_dynamic,
            _compute_dynamic,
            _is_rolling_vp,
            _compute_rolling_vp_dynamic,
        )

        name = self._name

        if name in _INDICATOR_HANDLERS:
            handler, _requires = _INDICATOR_HANDLERS[name]
            cache: dict = {}
            try:
                result = handler(df.copy(), name, cache)
                col = result[name]
                if hasattr(col, "iloc"):
                    return float(col.iloc[-1])
                return float(col)
            except Exception:
                return float("nan")

        if _is_dynamic(name):
            try:
                result = _compute_dynamic(df.copy(), name)
                col = result[name]
                if hasattr(col, "iloc"):
                    return float(col.iloc[-1])
                return float(col)
            except Exception:
                return float("nan")

        if _is_rolling_vp(name):
            try:
                result = _compute_rolling_vp_dynamic(df.copy(), name, {})
                col = result[name]
                if hasattr(col, "iloc"):
                    return float(col.iloc[-1])
                return float(col)
            except Exception:
                return float("nan")

        return float("nan")
