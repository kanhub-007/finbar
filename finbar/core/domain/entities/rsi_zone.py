"""RsiZone — 5‑tier RSI classification enum.

Domain concept, not tied to any specific calculator or data source.
"""

from enum import StrEnum


class RsiZone(StrEnum):
    """Five‑tier RSI zone classification.

    Mirrors H‑Stocks' Smart Cache thresholds validated against
    Wilder (30/70), Murphy, and crypto volatility research (20/80).
    """

    EXTREME_OVERSOLD = "EXTREME_OVERSOLD"
    """RSI < 20 — capitulation, very rare."""

    OVERSOLD = "OVERSOLD"
    """20 <= RSI < 30 — standard oversold (Wilder)."""

    NEUTRAL = "NEUTRAL"
    """30 <= RSI <= 70 — normal range."""

    OVERBOUGHT = "OVERBOUGHT"
    """70 < RSI <= 80 — standard overbought (Wilder)."""

    EXTREME_OVERBOUGHT = "EXTREME_OVERBOUGHT"
    """RSI > 80 — euphoria / blow‑off top."""
