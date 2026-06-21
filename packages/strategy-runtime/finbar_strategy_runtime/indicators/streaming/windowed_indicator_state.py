"""WindowedIndicatorState — bounded ring-buffer + recompute via batch handler.

Used for two classes of indicators:
- VP-prefix WINDOWED (e.g. ``rvp_poc_48``, ``vp_poc_10d``)
- Windowed-default (~183 indicators with registered handlers but no
  hand-written streaming state class).

Buffers bars in a ``deque(maxlen=window)`` and calls the registered
batch handler on the deque slice each update. Per-bar cost is O(window).

The buffer frame index is built from each bar's real ``timestamp`` when
present (int seconds, ISO strings, datetimes, or large-numeric
milliseconds). Session/date-sensitive indicators (``vp_*``, ``mp_*``,
``cvp_*``, AMT auction-state/signals) require real timestamps and raise
``ValueError`` when they are missing, so live-parity cannot be silently
broken by a fabricated ``2024-01-01`` index. Non-session indicators keep
a deterministic synthetic-index fallback.
"""

from __future__ import annotations

from collections import deque

import pandas as pd

# Numeric values at or above this threshold are interpreted as Unix
# milliseconds rather than seconds. Rationale: any plausible modern
# seconds timestamp is ~1.7e9, while millisecond timestamps are ~1.7e12.
# 1e11 seconds corresponds to year ~5138, so no realistic seconds value
# reaches it, and no modern millisecond value falls below it.
_MS_THRESHOLD = 1e11

# Synthetic fallback index origin for non-session indicators that lack
# real timestamps. Documented as NOT live-parity safe for any indicator
# whose value depends on date/session boundaries.
_FALLBACK_ORIGIN = "2024-01-01"

# Indicators whose value depends on per-session grouping or date
# boundaries. These MUST receive real bar timestamps; a fabricated
# index would silently corrupt session volume/market profiles and every
# AMT signal derived from them.
_SESSION_SENSITIVE_PREFIXES = ("vp_", "mp_", "cvp_")
_SESSION_SENSITIVE_NAMES = frozenset(
    {
        # Auction state (derived from session VP)
        "inside_value",
        "above_value",
        "below_value",
        "at_poc",
        "near_vah",
        "near_val",
        "distance_to_vah_pct",
        "distance_to_val_pct",
        "value_area_width_pct",
        "balance_status",
        # AMT rule signals
        "acceptance_into_value",
        "rejection_from_edge",
        "acceptance_outside_value",
        "poc_rejection",
        "edge_volume_building",
        "value_area_migration",
    }
)


def _is_session_sensitive(name: str) -> bool:
    """Return True if *name* is a session/date-sensitive indicator.

    Session-sensitive indicators group bars by calendar date (session VP,
    market profile, composite VP) or derive from columns that do (auction
    state, AMT signals). Rolling bar-window indicators such as ``rvp_*``
    are NOT session-sensitive.
    """
    if name in _SESSION_SENSITIVE_NAMES:
        return True
    return any(name.startswith(prefix) for prefix in _SESSION_SENSITIVE_PREFIXES)


def _parse_timestamp_index(timestamps: list) -> pd.DatetimeIndex:
    """Parse a list of timestamp values into a UTC DatetimeIndex.

    Supports:
    - int/float Unix seconds (Finbot/Hyperliquid production format)
    - int/float Unix milliseconds (auto-detected for large values)
    - ISO-8601 strings
    - Python ``datetime`` / ``pandas.Timestamp``

    Args:
        timestamps: Non-empty list of timestamp values of a single kind.

    Returns:
        A timezone-aware (UTC) DatetimeIndex.
    """
    first = timestamps[0]
    if isinstance(first, bool) or not isinstance(first, (int, float)):
        return pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True))
    unit = "ms" if abs(float(first)) >= _MS_THRESHOLD else "s"
    return pd.DatetimeIndex(pd.to_datetime(timestamps, unit=unit, utc=True))


class WindowedIndicatorState:
    """Bounded ring buffer that recomputes an indicator over the window.

    Stores at most ``maxlen`` bars. Each ``update()`` appends a bar,
    converts the deque to a DataFrame (preserving real bar timestamps),
    calls the registered batch handler, and returns the latest-row value
    for the indicator.
    """

    def __init__(self, name: str, maxlen: int) -> None:
        """Initialise with the indicator name and window size.

        Args:
            name: Indicator name (e.g. ``"bearish_fvg"``).
            maxlen: Maximum number of bars to retain (window size).
        """
        self._name = name
        self._buffer: deque[dict] = deque(maxlen=max(maxlen, 1))
        self._current: float = float("nan")

    def update(self, bar: dict) -> float:
        """Ingest one bar; recompute indicator and return latest value.

        Args:
            bar: OHLCV bar dict, optionally with a ``timestamp`` key.

        Returns:
            Latest indicator value, or NaN if window not full.

        Raises:
            ValueError: If the indicator is session-sensitive and the
                buffer contains bars without parseable timestamps.
        """
        self._buffer.append(bar)

        if len(self._buffer) < 2:
            return float("nan")

        df = self.to_frame()
        if df.empty:
            return float("nan")

        val = self._compute(df)
        self._current = val
        return val

    def to_frame(self) -> pd.DataFrame:
        """Convert the deque buffer to a DataFrame with a real timestamp index.

        The index is derived from each bar's ``timestamp`` field when
        present. Session-sensitive indicators raise ``ValueError`` if any
        bar lacks a timestamp; non-session indicators fall back to a
        deterministic synthetic index.

        Returns:
            DataFrame of the buffered bars with a DatetimeIndex.

        Raises:
            ValueError: For session-sensitive indicators when the buffer
                lacks parseable timestamps.
        """
        n = len(self._buffer)
        if n == 0:
            return pd.DataFrame()

        timestamps = [bar.get("timestamp") for bar in self._buffer]
        present = [t for t in timestamps if t is not None]

        if len(present) != n:
            # Missing or partial timestamps.
            if _is_session_sensitive(self._name):
                raise ValueError(
                    f"Indicator '{self._name}' is session/date-sensitive"
                    f" and requires real bar timestamps, but one or more"
                    f" buffered bars have no parseable 'timestamp' field."
                    f" Provide int-second, ISO-8601, or datetime timestamps."
                )
            index = pd.date_range(_FALLBACK_ORIGIN, periods=n, freq="h")
            return pd.DataFrame(list(self._buffer), index=index)

        index = _parse_timestamp_index(present)
        return pd.DataFrame(list(self._buffer), index=index)

    def reset(self) -> None:
        """Clear accumulated state."""
        self._buffer.clear()
        self._current = float("nan")

    @property
    def value(self) -> float:
        """Most recently computed value."""
        return self._current

    # ── internal ────────────────────────────────────────────────────────

    def _compute(self, df: pd.DataFrame) -> float:
        """Recompute the indicator over the window slice."""
        from finbar_strategy_runtime.indicators._dynamic_dispatch import (
            _compute_dynamic,
            _compute_rolling_vp_dynamic,
            _is_dynamic,
            _is_rolling_vp,
        )
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            _INDICATOR_HANDLERS,
            PandasTaIndicatorCalculator,
            _expand_transitive_deps,
        )

        name = self._name

        if name in _INDICATOR_HANDLERS:
            handler, _requires = _INDICATOR_HANDLERS[name]
            deps = [
                d
                for d in _expand_transitive_deps([name], _INDICATOR_HANDLERS)
                if d != name
            ]
            if deps:
                calc = PandasTaIndicatorCalculator()
                df = calc.calculate(df, deps)
            cache: dict = {}
            try:
                result = handler(df, name, cache)
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
