"""StreamingIndicatorEngine — concrete streaming indicator calculator.

Maps indicator names to per-indicator online state objects. Each
indicator name resolves via the classifier to a hand-written state
class (O(1)) or a windowed fallback (O(window)).

Multi-output states (MACD, BB) are deduplicated: requesting only
``macd_signal`` still creates the full ``MacdState``, so values are
always from a single source of truth.
"""

from __future__ import annotations

from math import isnan

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

    def __init__(self, indicators: list[str]) -> None:
        self._indicators = list(indicators)
        # name → state instance (for single-output states or shared family states)
        self._states: dict[str, object] = {}
        # family_key → state (the canonical state instance; multi-output
        # names share one)
        self._family_states: dict[str, object] = {}
        self._bars_seen: int = 0
        self._latest: LatestBar = LatestBar()

        for name in self._indicators:
            family = _canonical_family(name)
            if family not in self._family_states:
                self._family_states[family] = self._build_state(name)
            self._states[name] = self._family_states[family]

    # ── public API ──────────────────────────────────────────────────────

    def update(self, bar: dict) -> LatestBar:
        """Ingest one OHLCV bar; return the latest-row snapshot."""
        self._bars_seen += 1

        # Update each unique family state once
        for state in self._family_states.values():
            state.update(bar)

        # Read the output for each requested indicator name
        values: dict[str, float] = {}
        for name in self._indicators:
            state = self._states[name]
            val = self._read_output(name, state)
            if not isnan(val):
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
        for state in self._family_states.values():
            state.reset()
        self._bars_seen = 0
        self._latest = LatestBar()

    # ── output reading ──────────────────────────────────────────────────

    @staticmethod
    def _read_output(name: str, state: object) -> float:
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

        # Single-output: use .value property
        return getattr(state, "value", float("nan"))

    # ── internal state factory helpers ──────────────────────────────────

    @staticmethod
    def _make_sma(period: int) -> object:
        from finbar_strategy_runtime.indicators.streaming.sma_state import SmaState
        return SmaState(period)

    @staticmethod
    def _make_ema(period: int) -> object:
        from finbar_strategy_runtime.indicators.streaming.ema_state import EmaState
        return EmaState(period)

    @staticmethod
    def _make_rsi(period: int) -> object:
        from finbar_strategy_runtime.indicators.streaming.rsi_state import RsiState
        return RsiState(period)

    @staticmethod
    def _make_atr(period: int) -> object:
        from finbar_strategy_runtime.indicators.streaming.atr_state import AtrState
        return AtrState(period)

    @staticmethod
    def _make_adx(period: int) -> object:
        from finbar_strategy_runtime.indicators.streaming.adx_state import AdxState
        return AdxState(period)

    @staticmethod
    def _make_bb(period: int) -> object:
        from finbar_strategy_runtime.indicators.streaming.bb_state import BbState
        return BbState(period)

    @staticmethod
    def _make_macd() -> object:
        from finbar_strategy_runtime.indicators.streaming.macd_state import MacdState
        return MacdState()

    @staticmethod
    def _make_ibs() -> object:
        from finbar_strategy_runtime.indicators.streaming.ibs_state import IbsState
        return IbsState()

    @staticmethod
    def _make_vwap() -> object:
        from finbar_strategy_runtime.indicators.streaming.vwap_state import VwapState
        return VwapState()

    @staticmethod
    def _make_rvol() -> object:
        from finbar_strategy_runtime.indicators.streaming.rvol_state import RvolState
        return RvolState()

    @staticmethod
    def _make_ker() -> object:
        from finbar_strategy_runtime.indicators.streaming.ker_state import KerState
        return KerState()

    @staticmethod
    def _make_kama() -> object:
        from finbar_strategy_runtime.indicators.streaming.kama_state import KamaState
        return KamaState()

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

    @staticmethod
    def _resolve_window(name: str) -> int:
        """Resolve the window size for a windowed indicator."""
        from finbar_strategy_runtime.indicators._dynamic_dispatch import (
            _is_rolling_vp,
        )

        # VP-prefix: parse window from name suffix
        if _is_rolling_vp(name):
            return _parse_vp_window(name)

        # Session-count-based indicators (poc_slope_N, wyckoff_phase,
        # value_area_migration) group by calendar session and look back N
        # sessions. A bar-count window of 50 holds only 1-2 sessions for
        # intraday timeframes, so these indicators miscompute as 0.0. Use
        # a window large enough to cover the session lookback at the
        # production timeframes (30min=48 bars/session, 1h=24 bars/session).
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
        # Multi-output families
        if name in _MACD_NAMES:
            return self._make_macd()
        if name in _BB_NAMES:
            return self._make_bb(20)

        # Hand-listed names
        if name.startswith("sma_"):
            return self._make_sma(int(name[len("sma_"):]))
        if name.startswith("ema_"):
            return self._make_ema(int(name[len("ema_"):]))
        if name.startswith("rsi_"):
            return self._make_rsi(int(name[len("rsi_"):]))
        if name == "atr":
            return self._make_atr(14)
        if name.startswith("atr_"):
            return self._make_atr(int(name[len("atr_"):]))
        if name == "adx":
            return self._make_adx(14)

        # Dynamic-period names
        resolved = _resolve_dynamic(name)
        if resolved is not None:
            _func, _source_col, period, prefix = resolved
            handlers = {
                "sma": lambda p: self._make_sma(p),
                "ema": lambda p: self._make_ema(p),
                "rsi": lambda p: self._make_rsi(p),
                "atr": lambda p: self._make_atr(p),
                "adx": lambda p: self._make_adx(p),
                "bb_upper": lambda p: self._make_bb(p),
                "bb_middle": lambda p: self._make_bb(p),
                "bb_lower": lambda p: self._make_bb(p),
            }
            if prefix in handlers:
                return handlers[prefix](period)

        # Hand-listed non-parametric streaming indicators
        simple_states = {
            "vwap": self._make_vwap,
            "ibs": self._make_ibs,
            "rvol": self._make_rvol,
            "ker": self._make_ker,
            "kama": self._make_kama,
        }
        if name in simple_states:
            return simple_states[name]()

        raise NotImplementedError(f"Streaming state not yet implemented for: '{name}'")


# ── module-level helpers ────────────────────────────────────────────────────


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
# covers poc_slope_5 (6 sessions) at 30min (48 bars/session ≈ 8 sessions)
# and 1h (24 bars/session ≈ 20 sessions). poc_slope_20 on 30min needs
# ~1000 bars and is not used by the production strategy; documented as a
# future timeframe-aware-window improvement.
_SESSION_COUNT_WINDOW = 500
_SESSION_COUNT_NAMES = frozenset({"wyckoff_phase", "value_area_migration"})


def _session_count_window(name: str) -> int | None:
    """Return the window for session-count-based indicators, else None."""
    if name in _SESSION_COUNT_NAMES:
        return _SESSION_COUNT_WINDOW
    if name.startswith("poc_slope_"):
        return _SESSION_COUNT_WINDOW
    return None
