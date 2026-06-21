"""StreamingCoverageEntry — one metric's causal streaming coverage verdict."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_VALID_LABELS = frozenset({"STREAMING_CORRECT", "STREAMING_UNSUPPORTED"})


@dataclass(frozen=True)
class StreamingCoverageEntry:
    """Describes whether one metric is safe for causal streaming enrichment.

    Attributes:
        metric_name: Concrete catalog metric name.
        label: Either ``STREAMING_CORRECT`` or ``STREAMING_UNSUPPORTED``.
        reason: Human-readable reason for unsupported metrics.
        last_verified_at: Optional date/string describing when the verdict was
            generated.
        tolerance: Optional numeric tolerance metadata used by sweep tooling.
    """

    metric_name: str
    label: str
    reason: str = ""
    last_verified_at: str = ""
    tolerance: float | None = None

    def __post_init__(self) -> None:
        """Validate the coverage-entry invariants."""
        if self.label not in _VALID_LABELS:
            raise ValueError(f"Unknown streaming coverage label: {self.label}")
        if self.label == "STREAMING_UNSUPPORTED" and not self.reason:
            raise ValueError("Unsupported streaming metrics must include a reason")

    @classmethod
    def from_mapping(
        cls,
        metric_name: str,
        payload: dict[str, Any],
    ) -> StreamingCoverageEntry:
        """Create an entry from JSON-compatible coverage data.

        Args:
            metric_name: Concrete catalog metric name for the entry.
            payload: JSON-compatible entry payload.

        Returns:
            StreamingCoverageEntry built from the payload.
        """
        return cls(
            metric_name=metric_name,
            label=str(payload["label"]),
            reason=str(payload.get("reason", "")),
            last_verified_at=str(payload.get("last_verified_at", "")),
            tolerance=payload.get("tolerance"),
        )
