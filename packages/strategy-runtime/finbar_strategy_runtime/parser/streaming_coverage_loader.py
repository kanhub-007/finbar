"""Streaming coverage matrix loader — reads the bundled JSON resource.

This is the filesystem I/O boundary for
``StreamingCoverageMatrix``. The entity itself stays pure; loading happens
here so the entity is testable without any resource file.

Usage:

    from finbar_strategy_runtime.parser.streaming_coverage_loader import (
        load_default_streaming_coverage_matrix,
    )
    matrix = load_default_streaming_coverage_matrix()
"""

from __future__ import annotations

import json
from importlib import resources

from finbar_strategy_runtime.domain.entities.streaming_coverage_entry import (
    StreamingCoverageEntry,
)
from finbar_strategy_runtime.domain.entities.streaming_coverage_matrix import (
    StreamingCoverageMatrix,
)

_RESOURCE_PACKAGE = "finbar_strategy_runtime.resources"
_RESOURCE_NAME = "streaming_coverage_matrix.json"


def load_default_streaming_coverage_matrix() -> StreamingCoverageMatrix:
    """Load the package-bundled streaming coverage matrix.

    Reads ``streaming_coverage_matrix.json`` from the package resources and
    builds a frozen ``StreamingCoverageMatrix``.

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
    return StreamingCoverageMatrix(entries=entries)


__all__ = ["load_default_streaming_coverage_matrix"]
