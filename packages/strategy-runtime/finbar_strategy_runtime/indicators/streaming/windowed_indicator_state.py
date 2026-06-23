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

from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)

from finbar_strategy_runtime.indicators._bar_timestamp import (
    parse_bar_timestamps,
)

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


class WindowedIndicatorState(StreamingIndicatorState):
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

        index = parse_bar_timestamps(present)
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
        from finbar_strategy_runtime.indicators._compute_decorators import (
            resolve_last_value_compute,
        )
        from finbar_strategy_runtime.indicators._handler_registry import (
            default_handler_registry,
        )
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
            _expand_transitive_deps,
        )

        name = self._name
        handlers = default_handler_registry()

        # Pre-compute transitive dependencies (e.g. poc_slope_5 needs vp_poc)
        # so the resolved compute strategy finds them on the frame.
        if name in handlers:
            deps = [
                d
                for d in _expand_transitive_deps([name], handlers)
                if d != name
            ]
            if deps:
                calc = PandasTaIndicatorCalculator()
                df = calc.calculate(df, deps)

        compute = resolve_last_value_compute(name, handlers)
        return compute(df) if compute is not None else float("nan")


class BatchedWindowedState(StreamingIndicatorState):
    """Single ring buffer computing ALL windowed metrics in one batch call.

    Replaces N independent ``WindowedIndicatorState`` instances with one
    shared buffer. Converts bars to DataFrame **once** per update, runs
    the batch calculator **once** for all metrics, and returns a dict of
    ``{name: latest_value}``. On the AMT strategy this turns 10 batch
    calls per bar into 1 — an immediate ~10× speedup for both Finbar
    backtests and Finbot live/replay.
    """

    def __init__(self, names: list[str], maxlen: int) -> None:
        """Initialise with all metric names and a shared window size.

        Args:
            names: Concrete indicator names to compute together.
            maxlen: Maximum bars retained (use the max across all names).
        """
        self._names = list(names)
        self._maxlen = max(maxlen, 1)
        self._buffer: deque[dict] = deque(maxlen=self._maxlen)
        self._currents: dict[str, float] = {name: float("nan") for name in names}
        self._session_sensitive = any(
            _is_session_sensitive(name) for name in names
        )
        # Columns provided externally (e.g. VP from incremental state).
        # These are injected into the frame before batch compute so
        # dependent handlers find them without recomputing.
        self._injected_columns: dict[str, deque] = {}

    def set_injected_columns(self, column_names: list[str]) -> None:
        """Declare columns that will be injected each update.

        These columns (e.g. vp_poc/vp_vah/vp_val from incremental VP)
        are excluded from transitive dependency expansion and are
        expected to be provided via ``update(bar, injected_values)``.
        """
        for col in column_names:
            self._injected_columns[col] = deque(maxlen=self._maxlen)

    def update(self, bar: dict, injected_values: dict[str, float] | None = None) -> dict[str, float]:
        """Ingest one bar; recompute all metrics and return latest values.

        Args:
            bar: OHLCV bar dict, optionally with a ``timestamp`` key.
            injected_values: Pre-computed values for injected columns
                (e.g. VP from incremental state).

        Returns:
            Dict mapping metric name → latest value (NaN if not ready).

        Raises:
            ValueError: If any metric is session-sensitive and the
                buffer contains bars without parseable timestamps.
        """
        self._buffer.append(bar)
        if injected_values:
            for col, val in injected_values.items():
                if col in self._injected_columns:
                    self._injected_columns[col].append(val)
        if len(self._buffer) < 2:
            return {name: float("nan") for name in self._names}

        df = self._to_frame()
        if df.empty:
            return {name: float("nan") for name in self._names}

        # Inject pre-computed columns into the frame.
        for col, values_deque in self._injected_columns.items():
            if len(values_deque) == len(df):
                df[col] = list(values_deque)

        self._currents = self._compute_all(df)
        return dict(self._currents)

    def _to_frame(self) -> pd.DataFrame:
        """Convert the shared deque buffer to a timestamp-indexed DataFrame."""
        n = len(self._buffer)
        if n == 0:
            return pd.DataFrame()
        timestamps = [bar.get("timestamp") for bar in self._buffer]
        present = [t for t in timestamps if t is not None]
        if len(present) != n:
            if self._session_sensitive:
                raise ValueError(
                    "Batched windowed state contains session-sensitive"
                    " indicators and requires real bar timestamps, but"
                    " one or more buffered bars have no parseable"
                    " 'timestamp' field."
                )
            index = pd.date_range(_FALLBACK_ORIGIN, periods=n, freq="h")
            return pd.DataFrame(list(self._buffer), index=index)
        index = parse_bar_timestamps(present)
        return pd.DataFrame(list(self._buffer), index=index)

    def reset(self) -> None:
        """Clear accumulated state."""
        self._buffer.clear()
        for dq in self._injected_columns.values():
            dq.clear()
        self._currents = {name: float("nan") for name in self._names}

    @property
    def values(self) -> dict[str, float]:
        """Most recently computed values for all metrics."""
        return dict(self._currents)

    # ── internal ────────────────────────────────────────────────────────

    def _compute_all(self, df: pd.DataFrame) -> dict[str, float]:
        """Batch-compute all windowed metrics on the shared frame."""
        from finbar_strategy_runtime.indicators._dynamic_dispatch import (
            _compute_dynamic,
            _compute_rolling_vp_dynamic,
            _is_dynamic,
            _is_rolling_vp,
        )
        from finbar_strategy_runtime.indicators._handler_registry import (
            default_handler_registry,
        )
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
            _expand_transitive_deps,
        )

        # Collect all direct + transitive dependencies across all names,
        # EXCLUDING injected columns (they're already on the frame).
        handlers = default_handler_registry()
        all_deps: set[str] = set()
        injected = set(self._injected_columns.keys())
        for name in self._names:
            if name in handlers:
                all_deps.update(
                    d
                    for d in _expand_transitive_deps([name], handlers)
                    if d != name and d not in injected
                )

        # One-time pre-compute of all transitive dependencies.
        if all_deps:
            calc = PandasTaIndicatorCalculator()
            df = calc.calculate(df, sorted(all_deps))

        results: dict[str, float] = {}
        cache: dict = {}
        for name in self._names:
            results[name] = self._compute_one(df, name, cache)
        return results

    @staticmethod
    def _compute_one(
        df: pd.DataFrame,
        name: str,
        cache: dict,
    ) -> float:
        """Compute a single metric from the pre-enriched frame.

        The frame already carries all transitive dependencies (pre-computed
        by :meth:`_compute_all`), so this is a single strategy lookup + call.
        The ``cache`` is accepted for backward compatibility with handler
        signatures that take a cache dict; it is not used by the resolver
        because each windowed compute is independent.
        """
        from finbar_strategy_runtime.indicators._compute_decorators import (
            resolve_last_value_compute,
        )
        from finbar_strategy_runtime.indicators._handler_registry import (
            default_handler_registry,
        )

        compute = resolve_last_value_compute(name, default_handler_registry())
        return compute(df) if compute is not None else float("nan")
