"""StreamingWindowResolver — Strategy interface for window sizing.

Resolves the bounded streaming window (in bars) for a metric. Different
implementations can use different rules (interval-aware, catalog-based,
fixed). The streaming engine delegates session-count window sizing here.
"""

from __future__ import annotations

from typing import Protocol


class StreamingWindowResolver(Protocol):
    """Resolve the bounded streaming window (bars) for a metric.

    Returns the window size in bars, or ``None`` when this resolver does
    not own the metric (so the engine falls back to its default path).
    """

    def resolve(self, metric_name: str) -> int | None:
        """Return the window size for *metric_name*, or None if not owned."""
        ...


__all__ = ["StreamingWindowResolver"]
