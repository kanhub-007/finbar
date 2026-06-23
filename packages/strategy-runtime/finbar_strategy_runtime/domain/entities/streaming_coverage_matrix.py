"""StreamingCoverageMatrix — pure domain entity for streaming coverage data.

A frozen dataclass holding coverage entries keyed by metric name. Contains no
filesystem, network, or environment dependencies. Loading from the bundled
JSON resource is performed by the loader in
``finbar_strategy_runtime.parser.streaming_coverage_loader``.
"""

from __future__ import annotations

from dataclasses import dataclass

from finbar_strategy_runtime.domain.entities.streaming_coverage_entry import (
    StreamingCoverageEntry,
)
from finbar_strategy_runtime.domain.entities.unknown_metric_error import (
    UnknownMetricError,
)


@dataclass(frozen=True)
class StreamingCoverageMatrix:
    """Exhaustive streaming-correctness matrix for accepted strategy metrics.

    Pure data: entries keyed by lowercase concrete metric name. Construction
    and loading happen outside this class (see
    ``parser.streaming_coverage_loader``).
    """

    entries: dict[str, StreamingCoverageEntry]
    """Coverage entries keyed by concrete metric name."""

    def names(self) -> list[str]:
        """Return sorted metric names present in the matrix."""
        return sorted(self.entries)

    def entry_for(self, metric_name: str) -> StreamingCoverageEntry:
        """Return the coverage entry for a metric.

        Args:
            metric_name: Concrete metric name to look up.

        Returns:
            StreamingCoverageEntry for the requested metric.

        Raises:
            UnknownMetricError: If the matrix has no entry for the metric.
        """
        key = metric_name.lower()
        try:
            return self.entries[key]
        except KeyError as exc:
            raise UnknownMetricError(
                f"Unknown metric '{metric_name}' in streaming coverage matrix"
            ) from exc
