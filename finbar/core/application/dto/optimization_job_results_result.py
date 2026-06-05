"""Result DTO for optimization job results."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OptimizationJobResultsResult:
    """Completed optimization job with ranked results."""

    found: bool
    """True when the job exists."""

    job_id: str = ""
    status: str = ""
    metric: str = ""
    total_combinations: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
