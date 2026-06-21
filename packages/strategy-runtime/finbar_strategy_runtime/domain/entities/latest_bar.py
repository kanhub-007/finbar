"""LatestBar — immutable snapshot of streaming indicator values."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LatestBar:
    """Immutable value object holding the latest computed indicator scalars.

    Returned by ``StreamingIndicatorCalculator.update()`` and ``latest()``.
    """

    values: dict[str, Any] = field(default_factory=dict)
    """Indicator name → scalar value (number, string classifier, or bool)."""

    is_ready: bool = False
    """True once at least MIN_BARS bars have been ingested."""

    bars_seen: int = 0
    """Number of bars ingested so far (reset on ``reset()``)."""
