"""ConfidenceScore — multi-factor conviction score entity.

Domain concept — pure data, no behaviour, no external dependencies.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConfidenceScore:
    """0‑100 confidence score with additive component breakdown.

    Components follow the Smart Cache model: base + trend clarity
    + MTF alignment + breakout + volume + power zone, minus penalties
    for fakeout risk, overextension, and stale data.
    """

    score: int = 0
    """Final clamped score, 0–100."""

    base: int = 0
    """Base score from available timeframes (35 for 1d, 45 for 1d+1h)."""

    trend_clarity: int = 0
    """ADX bonus: +10 if ADX > 25 and direction is not neutral."""

    mtf_alignment: int = 0
    """MTF consensus: +15 FULL, +8 PARTIAL, 0 NEUTRAL/MIXED, -8 CONFLICTED."""

    breakout: int = 0
    """Breakout bonus: +10 CONFIRMED, +4 TRIGGERED."""

    volume: int = 0
    """Volume bonus: +5 RVOL >= 1.5, +8 RVOL >= 2.0, +12 RVOL >= 3.0."""

    power_zone: int = 0
    """+4 when breakout occurs at a power zone (multiple levels aligned)."""

    penalty: int = 0
    """Sum of all penalty deductions (fakeout, overextension, stale data)."""

    penalty_reasons: list[str] = field(default_factory=list)
    """Human-readable reasons for each penalty applied."""

    @property
    def is_tradeable(self) -> bool:
        """Score >= 30 is the minimum threshold for a tradeable setup."""
        return self.score >= 30

    @property
    def is_high_conviction(self) -> bool:
        """Score >= 70 indicates strong alignment and confirmation."""
        return self.score >= 70
