"""RiskFactor — actionable risk flags enum.

Domain concept — not tied to any specific data source or calculator.
"""

from enum import StrEnum


class RiskFactor(StrEnum):
    """Systematic risk flags for pre‑trade gating and size scaling."""

    AGAINST_BIAS = "AGAINST_BIAS"
    """Breakout/entry direction opposes the daily trend bias."""

    LOW_VOLUME = "LOW_VOLUME"
    """Daily RVOL < 0.5 — insufficient market participation."""

    WEAK_TREND = "WEAK_TREND"
    """ADX < 20 — no directional trend (Wilder standard)."""

    OVEREXTENDED_UP = "OVEREXTENDED_UP"
    """RSI > 80 — extreme overbought, blow‑off risk."""

    OVEREXTENDED_DOWN = "OVEREXTENDED_DOWN"
    """RSI < 20 — extreme oversold, capitulation risk."""

    NEAR_RESISTANCE = "NEAR_RESISTANCE"
    """Close within 0.5×ATR of swing_high — limited upside."""

    NEAR_SUPPORT = "NEAR_SUPPORT"
    """Close within 0.5×ATR of swing_low — limited downside."""

    BB_SQUEEZE = "BB_SQUEEZE"
    """BB width < 3% of price AND ADX < 20 — pending expansion."""

    STALE_DATA = "STALE_DATA"
    """Most recent bar is older than the expected interval."""
