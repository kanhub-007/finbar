"""StreamingCoverageMatrix — package-owned causal streaming coverage data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources

from finbar_strategy_runtime.domain.entities.streaming_coverage_entry import (
    StreamingCoverageEntry,
)
from finbar_strategy_runtime.domain.services.unknown_metric_error import (
    UnknownMetricError,
)

_RESOURCE_PACKAGE = "finbar_strategy_runtime.resources"
_RESOURCE_NAME = "streaming_coverage_matrix.json"


@dataclass(frozen=True)
class StreamingCoverageMatrix:
    """Exhaustive streaming-correctness matrix for accepted strategy metrics."""

    entries: dict[str, StreamingCoverageEntry]
    """Coverage entries keyed by concrete metric name."""

    @classmethod
    def load_default(cls) -> StreamingCoverageMatrix:
        """Load the package-bundled streaming coverage matrix.

        Returns:
            StreamingCoverageMatrix built from the package JSON resource.
        """
        path = resources.files(_RESOURCE_PACKAGE).joinpath(_RESOURCE_NAME)
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_entries = payload.get("entries", {})
        entries = {
            name: StreamingCoverageEntry.from_mapping(name, entry_payload)
            for name, entry_payload in raw_entries.items()
        }
        return cls(entries=entries)

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
