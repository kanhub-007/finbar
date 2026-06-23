"""StreamingStateFactory — registry mapping indicator names to state classes.

Replaces the per-engine ``_make_*`` static method explosion with one
registry. Each entry maps an exact name or a prefix to a factory that
builds the appropriate :class:`StreamingIndicatorState`.

The factory owns the lazy imports (breaking the import cycle with the
state modules), so the engine stays free of import boilerplate.
"""

from __future__ import annotations

from collections.abc import Callable

from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)


class StreamingStateFactory:
    """Build :class:`StreamingIndicatorState` instances by indicator name.

    Two registration styles:

    - ``register_exact(name, factory)`` — zero-arg factory for fixed names
      (``macd``, ``vwap``, ``ibs``, …).
    - ``register_prefix(prefix, factory)`` — ``factory(period: int)`` for
      parameterized names (``sma_`` → ``SmaState(period)``).
    """

    def __init__(self) -> None:
        self._exact: dict[str, Callable[[], StreamingIndicatorState]] = {}
        self._prefixed: list[tuple[str, Callable[[int], StreamingIndicatorState]]] = []

    def register_exact(
        self, name: str, factory: Callable[[], StreamingIndicatorState]
    ) -> None:
        """Register a zero-arg factory for an exact indicator name."""
        self._exact[name] = factory

    def register_prefix(
        self, prefix: str, factory: Callable[[int], StreamingIndicatorState]
    ) -> None:
        """Register a factory taking a period for a name prefix.

        ``prefix`` must include the trailing underscore (e.g. ``"sma_"``).
        """
        self._prefixed.append((prefix, factory))

    def build(self, name: str) -> StreamingIndicatorState | None:
        """Build the state for *name*, or None if no factory matches."""
        if name in self._exact:
            return self._exact[name]()
        for prefix, factory in self._prefixed:
            if name.startswith(prefix):
                rest = name[len(prefix):]
                if rest.isdigit():
                    period = int(rest)
                    if period >= 2:
                        return factory(period)
        return None


def default_streaming_state_factory() -> StreamingStateFactory:
    """Build the default factory populated with every hand-written state.

    Imports are deferred to call time to avoid an import cycle (state
    modules import other package modules that eventually import this one).
    """
    factory = StreamingStateFactory()

    # ── exact (fixed) names ────────────────────────────────────────────
    def _macd() -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.macd_state import MacdState
        return MacdState()

    def _vwap() -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.vwap_state import VwapState
        return VwapState()

    def _ibs() -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.ibs_state import IbsState
        return IbsState()

    def _rvol() -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.rvol_state import RvolState
        return RvolState()

    def _ker() -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.ker_state import KerState
        return KerState()

    def _kama() -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.kama_state import KamaState
        return KamaState()

    def _atr14() -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.atr_state import AtrState
        return AtrState(14)

    def _adx14() -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.adx_state import AdxState
        return AdxState(14)

    def _bb20() -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.bb_state import BbState
        return BbState(20)

    for name, fn in (
        ("macd", _macd),
        ("macd_signal", _macd),
        ("macd_hist", _macd),
        ("vwap", _vwap),
        ("ibs", _ibs),
        ("rvol", _rvol),
        ("ker", _ker),
        ("kama", _kama),
        ("atr", _atr14),
        ("adx", _adx14),
    ):
        factory.register_exact(name, fn)
    # BB family is registered both as exact "bb_upper/middle/lower" handled
    # by the engine's family logic and as a prefix for dynamic periods.
    for bb_name in ("bb_upper", "bb_middle", "bb_lower"):
        factory.register_exact(bb_name, _bb20)

    # ── prefixed (parameterized) names ─────────────────────────────────
    def _sma(period: int) -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.sma_state import SmaState
        return SmaState(period)

    def _ema(period: int) -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.ema_state import EmaState
        return EmaState(period)

    def _rsi(period: int) -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.rsi_state import RsiState
        return RsiState(period)

    def _atr(period: int) -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.atr_state import AtrState
        return AtrState(period)

    def _adx(period: int) -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.adx_state import AdxState
        return AdxState(period)

    def _bb(period: int) -> StreamingIndicatorState:
        from finbar_strategy_runtime.indicators.streaming.bb_state import BbState
        return BbState(period)

    for prefix, fn in (
        ("sma_", _sma),
        ("ema_", _ema),
        ("rsi_", _rsi),
        ("atr_", _atr),
        ("adx_", _adx),
        ("bb_upper_", _bb),
        ("bb_middle_", _bb),
        ("bb_lower_", _bb),
    ):
        factory.register_prefix(prefix, fn)

    return factory


__all__ = ["StreamingStateFactory", "default_streaming_state_factory"]
