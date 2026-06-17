"""Streaming indicator classifier — resolves indicator names to dispatch kinds.

Four-tier resolution (evaluated in order, per 03-domain.md):

1. Hand-listed STREAMING — O(1) online state classes.
2. Dynamic-period STREAMING — ``sma_N``, ``ema_N``, ``rsi_N``, etc.
3. VP-prefix WINDOWED — ``rvp_*``, ``vp_*Nd``, ``cvp_*Nd``.
4. Windowed-default — any other registered handler → WINDOWED with
   window = ``max(min_lookback, MIN_BARS)``.
5. UNKNOWN — no handler, no pattern → raises at construction.
"""

from __future__ import annotations

from enum import Enum


class IndicatorKind(Enum):
    """Classification of an indicator name for engine dispatch."""

    STREAMING = "STREAMING"
    WINDOWED = "WINDOWED"
    UNKNOWN = "UNKNOWN"


class UnsupportedStreamingIndicatorError(ValueError):
    """Raised when an indicator name has no registered handler and no
    matching dynamic/VP pattern — a genuinely unknown metric."""


# ── Tier 1: Hand-listed STREAMING indicators ────────────────────────────────
# These are the indicators with hand-written state classes.

_HAND_STREAMING: frozenset[str] = frozenset(
    {
        "sma_10",
        "sma_20",
        "sma_50",
        "sma_200",
        "ema_12",
        "ema_26",
        "rsi_7",
        "rsi_14",
        "atr",
        "adx",
        "macd",
        "macd_signal",
        "macd_hist",
        "bb_upper",
        "bb_middle",
        "bb_lower",
        "ker",
        "kama",
        "vwap",
        "ibs",
        "rvol",
    }
)

# ── Public API ───────────────────────────────────────────────────────────────


def classify_indicator(name: str) -> IndicatorKind:
    """Classify an indicator name for streaming engine dispatch.

    Args:
        name: Indicator name (e.g. ``"sma_20"``, ``"bearish_fvg"``).

    Returns:
        ``IndicatorKind.STREAMING`` for O(1) online indicators,
        ``IndicatorKind.WINDOWED`` for bounded-window fallback.

    Raises:
        UnsupportedStreamingIndicatorError: If the name is genuinely
            unknown (no registered handler, no dynamic/VP pattern).
    """
    # Tier 1: Hand-listed STREAMING
    if name in _HAND_STREAMING:
        return IndicatorKind.STREAMING

    # Tier 2: Dynamic-period STREAMING (sma_N, ema_N, rsi_N, etc.)
    from finbar_strategy_runtime.indicators._dynamic_dispatch import (
        _is_dynamic,
    )

    if _is_dynamic(name):
        return IndicatorKind.STREAMING

    # Tier 3: VP-prefix WINDOWED (rvp_*, vp_*Nd, cvp_*Nd)
    from finbar_strategy_runtime.indicators._dynamic_dispatch import (
        _is_rolling_vp,
    )

    if _is_rolling_vp(name):
        return IndicatorKind.WINDOWED

    # Tier 4: Windowed-default — any other registered handler
    from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
        _INDICATOR_HANDLERS,
    )

    if name in _INDICATOR_HANDLERS:
        return IndicatorKind.WINDOWED

    # Tier 5: UNKNOWN — genuinely unknowable
    raise UnsupportedStreamingIndicatorError(
        f"Unknown streaming indicator: '{name}' — "
        f"no registered handler and no matching dynamic/VP pattern"
    )
