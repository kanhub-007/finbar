"""StreamingCoverageReport — aggregate verdict for a metric set."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StreamingCoverageReport:
    """Reports streaming coverage for a collection of metric names.

    Attributes:
        correct: Metrics that are safe to compute through causal streaming.
        unsupported: Metrics that must not silently drive causal streaming.
        silent_wrong: Unsupported metrics known to return wrong values.
        loud_nan_mismatch: Unsupported metrics known to NaN/raise incorrectly.
    """

    correct: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    silent_wrong: list[str] = field(default_factory=list)
    loud_nan_mismatch: list[str] = field(default_factory=list)

    @property
    def live_parity_safe(self) -> bool:
        """Return True when no metric blocks causal streaming."""
        return not self.unsupported
