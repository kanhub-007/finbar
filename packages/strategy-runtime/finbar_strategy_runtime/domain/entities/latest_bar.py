"""LatestBar — immutable snapshot of streaming indicator values."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LatestBar:
    """Immutable value object holding the latest computed indicator scalars.

    Returned by ``StreamingIndicatorCalculator.update()`` and ``latest()``.
    """

    values: dict[str, float] = field(default_factory=dict)
    """Indicator name → scalar value (e.g. ``{"sma_20": 100.5, "rsi_14": 55.0}``)."""

    is_ready: bool = False
    """True once at least MIN_BARS bars have been ingested."""

    bars_seen: int = 0
    """Number of bars ingested so far (reset on ``reset()``)."""
