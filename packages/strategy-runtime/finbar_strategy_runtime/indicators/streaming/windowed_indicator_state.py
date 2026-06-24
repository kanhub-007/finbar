"""WindowedIndicatorState — bounded ring-buffer + recompute via batch handler.

Used for two classes of indicators:
- VP-prefix WINDOWED (e.g. ``rvp_poc_48``, ``vp_poc_10d``)
- Windowed-default (~183 indicators with registered handlers but no
  hand-written streaming state class).

Buffers bars in a ``deque(maxlen=window)`` and calls the registered
batch handler on the deque slice each update. Per-bar cost is O(window).

The buffer frame index is built from each bar's real ``timestamp``
(int seconds, ISO strings, datetimes, or large-numeric milliseconds).
All windowed streaming indicators require real timestamps and raise
``ValueError`` when they are missing, so live-parity cannot be silently
broken by a fabricated date index.
"""

from __future__ import annotations

from collections import deque

import pandas as pd

from finbar_strategy_runtime.indicators._bar_timestamp import (
    parse_bar_timestamps,
)
from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)

# All windowed streaming indicators require real bar timestamps: a
# fabricated index would make session/date-sensitive metrics (session
# VP, market profile, AMT signals, etc.) silently wrong. Missing
# timestamps therefore raise ``ValueError`` rather than fall back to a
# synthetic date index.


class WindowedIndicatorState(StreamingIndicatorState):
    """Bounded ring buffer that recomputes an indicator over the window.

    Stores at most ``maxlen`` bars. Each ``update()`` appends a bar,
    converts the deque to a DataFrame (preserving real bar timestamps),
    calls the registered batch handler, and returns the latest-row value
    for the indicator.

    Maintains an incremental DataFrame to avoid full deque→DataFrame
    conversion on every bar — only the new row is allocated.
    """

    def __init__(self, name: str, maxlen: int) -> None:
        """Initialise with the indicator name and window size.

        Args:
            name: Indicator name (e.g. ``"bearish_fvg"``).
            maxlen: Maximum number of bars to retain (window size).
        """
        self._name = name
        self._maxlen = max(maxlen, 1)
        self._buffer: deque[dict] = deque(maxlen=self._maxlen)
        self._current: float = float("nan")
        # Incremental frame: built once from the deque, then maintained
        # row-by-row to avoid O(window) list→DataFrame per bar.
        self._frame: pd.DataFrame | None = None

    def update(self, bar: dict) -> float:
        """Ingest one bar; recompute indicator and return latest value.

        Args:
            bar: OHLCV bar dict, optionally with a ``timestamp`` key.

        Returns:
            Latest indicator value, or NaN if window not full.

        Raises:
            ValueError: If the buffer contains bars without parseable
                timestamps.
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
        """Return the maintained DataFrame, building it incrementally.

        On first call, builds from the full deque. Thereafter, only
        appends the single new row (or pops the oldest if at capacity).

        Returns:
            DataFrame of the buffered bars with a DatetimeIndex.

        Raises:
            ValueError: When the buffer lacks parseable timestamps.
        """
        n = len(self._buffer)
        if n == 0:
            return pd.DataFrame()

        # Check that all bars have timestamps (validation only).
        timestamps = [bar.get("timestamp") for bar in self._buffer]
        present = [t for t in timestamps if t is not None]
        if len(present) != n:
            raise ValueError(
                f"Indicator '{self._name}' requires real bar timestamps,"
                f" but one or more buffered bars have no parseable"
                f" 'timestamp' field. Provide int-second, ISO-8601,"
                f" or datetime timestamps."
            )

        if self._frame is not None:
            # Incremental: append the single new bar (last in deque).
            new_bar = self._buffer[-1]
            new_ts = parse_bar_timestamps([new_bar["timestamp"]])[0]
            new_row = pd.DataFrame([new_bar], index=[new_ts])
            self._frame = pd.concat(
                [self._frame, new_row]
            )
        else:
            # First call: build from the full deque.
            index = parse_bar_timestamps(present)
            self._frame = pd.DataFrame(list(self._buffer), index=index)

        # Trim to window size: drop oldest row(s) if over capacity.
        if len(self._frame) > self._maxlen:
            self._frame = self._frame.iloc[-self._maxlen:]

        return self._frame

    def reset(self) -> None:
        """Clear accumulated state."""
        self._buffer.clear()
        self._current = float("nan")
        self._frame = None

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

    Maintains an incremental DataFrame to avoid full deque→DataFrame
    conversion on every bar.
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
        # Incremental frame: built once, then maintained row-by-row.
        self._frame: pd.DataFrame | None = None
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

    def update(
        self, bar: dict, injected_values: dict[str, float] | None = None
    ) -> dict[str, float]:
        """Ingest one bar; recompute all metrics and return latest values.

        Args:
            bar: OHLCV bar dict, optionally with a ``timestamp`` key.
            injected_values: Pre-computed values for injected columns
                (e.g. VP from incremental state).

        Returns:
            Dict mapping metric name → latest value (NaN if not ready).

        Raises:
            ValueError: If any buffered bar lacks a parseable timestamp.
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
        """Return the maintained DataFrame, building it incrementally.

        On first call, builds from the full deque. Thereafter only
        appends the single new row. Avoids O(window) list→DataFrame
        conversion on every bar.
        """
        n = len(self._buffer)
        if n == 0:
            return pd.DataFrame()
        timestamps = [bar.get("timestamp") for bar in self._buffer]
        present = [t for t in timestamps if t is not None]
        if len(present) != n:
            raise ValueError(
                "Batched windowed state requires real bar timestamps, but"
                " one or more buffered bars have no parseable 'timestamp'"
                " field."
            )

        if self._frame is not None:
            # Incremental: append the single new bar.
            new_bar = self._buffer[-1]
            new_ts = parse_bar_timestamps([new_bar["timestamp"]])[0]
            new_row = pd.DataFrame([new_bar], index=[new_ts])
            self._frame = pd.concat(
                [self._frame, new_row]
            )
        else:
            # First call: build from the full deque.
            index = parse_bar_timestamps(present)
            self._frame = pd.DataFrame(list(self._buffer), index=index)

        # Trim to window size.
        if len(self._frame) > self._maxlen:
            self._frame = self._frame.iloc[-self._maxlen:]

        return self._frame

    def reset(self) -> None:
        """Clear accumulated state."""
        self._buffer.clear()
        for dq in self._injected_columns.values():
            dq.clear()
        self._currents = {name: float("nan") for name in self._names}
        self._frame = None

    @property
    def values(self) -> dict[str, float]:
        """Most recently computed values for all metrics."""
        return dict(self._currents)

    # ── internal ────────────────────────────────────────────────────────

    def _compute_all(self, df: pd.DataFrame) -> dict[str, float]:
        """Batch-compute all windowed metrics on the shared frame."""
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
