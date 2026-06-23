"""StreamingIndicatorEngine — concrete streaming indicator calculator.

Maps indicator names to per-indicator online state objects. Each
indicator name resolves via the classifier to a hand-written state
class (O(1)) or a windowed fallback (O(window)).

Multi-output states (MACD, BB) are deduplicated: requesting only
``macd_signal`` still creates the full ``MacdState``, so values are
always from a single source of truth.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from finbar_strategy_runtime.domain.entities.latest_bar import LatestBar
from finbar_strategy_runtime.domain.interfaces.streaming_indicator_calculator import (
    StreamingIndicatorCalculator,
)
from finbar_strategy_runtime.indicators._dynamic_dispatch import (
    _resolve_dynamic,
)
from finbar_strategy_runtime.indicators._streaming_classifier import (
    IndicatorKind,
    UnsupportedStreamingIndicatorError,
    classify_indicator,
)

MIN_BARS = 10

# ── multi-output family mappings ────────────────────────────────────────────
# Each family key maps to a set of indicator names served by one state class.

_MACD_NAMES = frozenset({"macd", "macd_signal", "macd_hist"})
_BB_NAMES = frozenset({"bb_upper", "bb_middle", "bb_lower"})
# Dynamic bb_upper_N / bb_middle_N / bb_lower_N share the same family

_MULTI_OUTPUT_FAMILIES: dict[str, frozenset[str]] = {
    "macd": _MACD_NAMES,
    "bb": _BB_NAMES,
}


def _canonical_family(name: str) -> str:
    """Return the canonical family key for a multi-output indicator,
    or *name* itself for single-output ones."""
    if name in _MACD_NAMES:
        return "macd"
    if name in _BB_NAMES:
        return "bb"
    # Dynamic BB names
    for prefix in ("bb_upper_", "bb_middle_", "bb_lower_"):
        if name.startswith(prefix):
            return "bb"
    return name


class StreamingIndicatorEngine(StreamingIndicatorCalculator):
    """Maps indicator names to per-indicator online state objects."""

    def __init__(
        self,
        indicators: list[str],
        window_resolver: object | None = None,
    ) -> None:
        self._indicators = list(indicators)
        # Optional interval-aware window resolver for session-count metrics.
        # When None, session-count metrics keep their existing (fixed) window
        # resolution for backward compatibility.
        self._window_resolver = window_resolver
        # name → state instance (for single-output states or shared family states)
        self._states: dict[str, object] = {}
        # family_key → state (the canonical state instance; multi-output
        # names share one)
        self._family_states: dict[str, object] = {}
        # Batched windowed state — all scalar-windowed metrics on this
        # timeframe share ONE ring buffer + ONE batch compute pass per bar.
        self._batched_windowed: object | None = None
        # Incremental session VP state — shared by vp_poc / vp_vah / vp_val.
        self._session_vp: object | None = None
        self._bars_seen: int = 0
        self._latest: LatestBar = LatestBar()

        # First pass: classify indicators, collecting windowed names
        windowed_names: list[str] = []
        from finbar_strategy_runtime.indicators.streaming import (
            prefix_recompute_indicator_state as _prefix_state,
        )
        from finbar_strategy_runtime.indicators.streaming import (
            rolling_volume_profile_state as _rvp_state,
        )

        # Session VP metrics get an incremental state. This is also created
        # when a requested metric TRANSITIVELY depends on vp_* (e.g. derived
        # AMT metrics like near_vah) so the windowed fallback receives the
        # correct expanding-session VP instead of computing it on a truncated
        # trailing window.
        needs_session_vp = any(
            name in _VP_ROOT_NAMES for name in self._indicators
        ) or (_any_transitive_depends_on_vp(self._indicators))
        if needs_session_vp:
            from finbar_strategy_runtime.indicators.streaming.incremental_session_vp_state import (  # noqa: E501
                IncrementalSessionVpState,
            )
            self._session_vp = IncrementalSessionVpState()

        for name in self._indicators:
            if _prefix_state.is_prefix_recompute_metric(name):
                continue  # prefix-recompute is separate
            if _rvp_state.is_rolling_volume_profile_metric(name):
                continue  # RVP has own state
            if name in _VP_ROOT_NAMES:
                continue  # incremental VP, not windowed
            family = _canonical_family(name)
            kind = classify_indicator(name)
            if kind == IndicatorKind.WINDOWED and family == name:
                # Scalar-windowed — candidate for batching
                windowed_names.append(name)

        # Batch the windowed metrics when there are at least two, OR when VP
        # injection is needed: a single derived-AMT windowed metric must still
        # go through the batched state so the injected vp_* columns reach its
        # batch compute pass (a standalone WindowedIndicatorState has no
        # injection hook and would recompute VP on a truncated window).
        if len(windowed_names) >= 2 or (
            len(windowed_names) == 1 and self._session_vp is not None
        ):
            from finbar_strategy_runtime.indicators.streaming.windowed_indicator_state import (  # noqa: E501
                BatchedWindowedState,
            )

            batched_window = max(
                self._resolve_window(name) for name in windowed_names
            )
            self._batched_windowed = BatchedWindowedState(
                names=windowed_names,
                maxlen=batched_window,
            )
            if self._session_vp is not None:
                self._batched_windowed.set_injected_columns(
                    ["vp_poc", "vp_vah", "vp_val"]
                )

        for name in self._indicators:
            if name in _VP_ROOT_NAMES and self._session_vp is not None:
                self._states[name] = self._session_vp
                continue
            family = _canonical_family(name)
            if self._batched_windowed is not None and name in windowed_names:
                self._family_states[family] = self._batched_windowed
            elif family not in self._family_states:
                self._family_states[family] = self._build_state(name)
            self._states[name] = self._family_states[family]

        # De-duplicated family states (the batched state appears under
        # multiple family keys but is one shared object). Built once here
        # so update()/reset() iterate without per-bar id() bookkeeping.
        # The batched_windowed state is EXCLUDED: it is updated separately
        # in update() with injected VP values, so it must not be updated
        # again in the family-state loop (a double update would corrupt
        # its ring buffer and break VP-injection deque alignment).
        unique: list[object] = []
        seen_ids: set[int] = set()
        if self._batched_windowed is not None:
            seen_ids.add(id(self._batched_windowed))
        for state in self._family_states.values():
            if id(state) in seen_ids:
                continue
            seen_ids.add(id(state))
            unique.append(state)
        self._unique_family_states: list[object] = unique

    # ── public API ──────────────────────────────────────────────────────

    def update(self, bar: dict) -> LatestBar:
        """Ingest one OHLCV bar; return the latest-row snapshot."""
        self._bars_seen += 1

        # Update each unique family state once. ``_unique_states`` is the
        # de-duplicated set built in __init__, so no per-bar id() dance.
        if self._session_vp is not None:
            self._session_vp.update(bar)
        if self._batched_windowed is not None:
            injected = {}
            if self._session_vp is not None:
                injected = {
                    "vp_poc": self._session_vp.poc,
                    "vp_vah": self._session_vp.vah,
                    "vp_val": self._session_vp.val,
                }
            self._batched_windowed.update(bar, injected_values=injected)
        for state in self._unique_family_states:
            state.update(bar)

        # Read the output for each requested indicator name
        values: dict[str, Any] = {}
        for name in self._indicators:
            state = self._states[name]
            val = self._read_output(name, state)
            if not _is_missing_value(val):
                values[name] = val

        self._latest = LatestBar(
            values=values,
            is_ready=self._bars_seen >= MIN_BARS,
            bars_seen=self._bars_seen,
        )
        return self._latest

    def latest(self) -> LatestBar:
        return self._latest

    def is_ready(self) -> bool:
        return self._bars_seen >= MIN_BARS

    def reset(self) -> None:
        if self._session_vp is not None:
            self._session_vp.reset()
        if self._batched_windowed is not None:
            self._batched_windowed.reset()
        for state in self._unique_family_states:
            state.reset()
        self._bars_seen = 0
        self._latest = LatestBar()

    # ── output reading ──────────────────────────────────────────────────

    @staticmethod
    def _read_output(name: str, state: object) -> Any:
        """Read the scalar output for *name* from *state*.

        Single-output states use their ``.value`` property.
        Multi-output states use named properties.
        """
        # Multi-output: MACD family
        if name in _MACD_NAMES:
            if name == "macd":
                return getattr(state, "macd", float("nan"))
            if name == "macd_signal":
                return getattr(state, "signal", float("nan"))
            if name == "macd_hist":
                return getattr(state, "hist", float("nan"))

        # Multi-output: BB family
        if name in _BB_NAMES or name.startswith("bb_"):
            if name == "bb_upper" or name.startswith("bb_upper"):
                return getattr(state, "upper", float("nan"))
            if name == "bb_middle" or name.startswith("bb_middle"):
                return getattr(state, "middle", float("nan"))
            if name == "bb_lower" or name.startswith("bb_lower"):
                return getattr(state, "lower", float("nan"))

        # Session VP: read from incremental state properties
        if name == "vp_poc":
            return getattr(state, "poc", float("nan"))
        if name == "vp_vah":
            return getattr(state, "vah", float("nan"))
        if name == "vp_val":
            return getattr(state, "val", float("nan"))

        # Single-output: use .value property, or .values[name] for batched state.
        if hasattr(state, "values"):
            return state.values.get(name, float("nan"))
        return getattr(state, "value", float("nan"))

    # ── internal ────────────────────────────────────────────────────────

    def _build_state(self, name: str) -> object:
        """Build the per-indicator state object for *name*."""
        from finbar_strategy_runtime.indicators.streaming import (
            prefix_recompute_indicator_state as prefix_state,
        )

        if prefix_state.is_prefix_recompute_metric(name):
            return prefix_state.PrefixRecomputeIndicatorState(name)
        kind = classify_indicator(name)
        if kind == IndicatorKind.STREAMING:
            return self._build_streaming_state(name)
        if kind == IndicatorKind.WINDOWED:
            return self._build_windowed_state(name)
        raise UnsupportedStreamingIndicatorError(
            f"Unknown indicator: '{name}'"
        )

    def _build_windowed_state(self, name: str) -> object:
        """Build the appropriate state for a windowed indicator."""
        from finbar_strategy_runtime.indicators.streaming import (
            prefix_recompute_indicator_state as prefix_state,
        )
        from finbar_strategy_runtime.indicators.streaming import (
            rolling_volume_profile_state as rvp_state,
        )
        from finbar_strategy_runtime.indicators.streaming import (
            windowed_indicator_state,
        )

        if rvp_state.is_rolling_volume_profile_metric(name):
            return rvp_state.RollingVolumeProfileState(name)
        if prefix_state.is_prefix_recompute_metric(name):
            return prefix_state.PrefixRecomputeIndicatorState(name)
        window = self._resolve_window(name)
        return windowed_indicator_state.WindowedIndicatorState(name=name, maxlen=window)

    def _resolve_window(self, name: str) -> int:
        """Resolve the window size for a windowed indicator."""
        from finbar_strategy_runtime.indicators._dynamic_dispatch import (
            _is_rolling_vp,
        )

        # VP-prefix: parse window from name suffix
        if _is_rolling_vp(name):
            return _parse_vp_window(name)

        # Session-count-based indicators (poc_slope_N, wyckoff_phase,
        # value_area_migration) group by calendar session and look back N
        # sessions. When an interval-aware resolver is provided, use it; it
        # raises for unknown intervals instead of silently using a fixed
        # window. Without a resolver, keep the existing fixed window.
        if self._window_resolver is not None:
            resolved = self._window_resolver.resolve(name)
            if resolved is not None:
                return resolved
        session_window = _session_count_window(name)
        if session_window is not None:
            return session_window

        # Windowed-default: use UnifiedMetricCatalog min_lookback
        # Floor at 50 to ensure handlers with large internal warmup
        # (e.g. awesome_oscillator needs 34 bars) still compute correctly.
        try:
            from finbar_strategy_runtime.parser.unified_metric_catalog import (
                UnifiedMetricCatalog,
            )

            catalog = UnifiedMetricCatalog()
            definition = catalog.get(name)
            if definition is not None:
                return max(definition.min_lookback, 50)
        except Exception:
            pass

        return 50

    def _build_streaming_state(self, name: str) -> object:
        """Build a streaming state via the factory registry.

        The factory resolves exact names (``macd``, ``vwap``, ...), the BB
        family, and prefixed names (``sma_N``, ``rsi_N``, ...). Dynamic
        period names (e.g. ``bb_upper_30``) that the factory does not
        recognise directly are resolved via :func:`_resolve_dynamic` and
        retried against the factory under their canonical prefixed form.
        """
        from finbar_strategy_runtime.indicators.streaming import (
            _streaming_state_factory as factory_mod,
        )

        state = factory_mod.default_streaming_state_factory().build(name)
        if state is not None:
            return state

        # Dynamic-period names the factory did not match directly.
        resolved = _resolve_dynamic(name)
        if resolved is not None:
            _func, _source_col, period, prefix = resolved
            canonical = f"{prefix}_{period}"
            state = factory_mod.default_streaming_state_factory().build(canonical)
            if state is not None:
                return state

        raise NotImplementedError(f"Streaming state not yet implemented for: '{name}'")


# ── module-level helpers ────────────────────────────────────────────────────


def _is_missing_value(value: Any) -> bool:
    """Return True for scalar missing/NaN values."""
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    try:
        return bool(missing)
    except ValueError:
        return False


_VP_ROOT_NAMES = frozenset({"vp_poc", "vp_vah", "vp_val"})


def _any_transitive_depends_on_vp(indicators: list[str]) -> bool:
    """Return True if any requested metric transitively requires vp_*.

    Walks the handler ``requires`` graph so derived AMT metrics (near_vah,
    rejection_from_edge, etc.) trigger incremental session VP injection
    even when ``vp_poc/vp_vah/vp_val`` are not requested explicitly.
    """
    from finbar_strategy_runtime.indicators._handler_registry import (
        default_handler_registry,
    )

    handlers = default_handler_registry()
    seen: set[str] = set()
    stack = [n for n in indicators if n not in _VP_ROOT_NAMES]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        if name not in handlers:
            continue
        _fn, requires = handlers[name]
        for dep in requires:
            if dep in _VP_ROOT_NAMES:
                return True
            if dep not in seen:
                stack.append(dep)
    return False



def _parse_vp_window(name: str) -> int:
    """Parse window size from a VP-prefix indicator name.

    Examples:
        ``rvp_poc_48`` → 48
        ``vp_poc_10d`` → 10
        ``cvp_poc_5d`` → 5
    """
    from finbar_strategy_runtime.indicators._dynamic_dispatch import (
        _CVP_PREFIXES,
        _ROLLING_VP_PREFIXES,
        _RVP_PREFIXES,
    )

    for prefix in _RVP_PREFIXES:
        if name.startswith(prefix):
            inner = name[len(prefix):]
            if inner.isdigit():
                return max(int(inner), MIN_BARS)
    for prefix in _ROLLING_VP_PREFIXES | _CVP_PREFIXES:
        if name.startswith(prefix) and name.endswith("d"):
            inner = name[len(prefix):-1]
            if inner.isdigit():
                return max(int(inner), MIN_BARS)
    return MIN_BARS


# Window floor for session-count-based indicators (poc_slope_N,
# wyckoff_phase, value_area_migration). These look back N sessions; a
# 50-bar window holds too few sessions at intraday timeframes. 500 bars
# covers poc_slope_5 (6 sessions) at 30min (48 bars/session ~ 8 sessions)
# and 1h (24 bars/session ~ 20 sessions). Interval-aware window sizing
# is deferred to a follow-up (spec: 2026-06-22_streaming-performance).
_SESSION_COUNT_WINDOW = 500
_SESSION_COUNT_NAMES = frozenset({"wyckoff_phase", "value_area_migration"})


def _session_count_window(name: str) -> int | None:
    """Return the session-count window for *name*, or None."""
    if name in _SESSION_COUNT_NAMES:
        return _SESSION_COUNT_WINDOW
    if name.startswith("poc_slope_"):
        return _SESSION_COUNT_WINDOW
    return None
