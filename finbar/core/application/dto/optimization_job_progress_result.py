"""Result DTO for optimization job progress."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OptimizationJobProgressResult:
    """Current progress state for an optimization job."""

    found: bool
    """True when the job exists."""

    job_id: str = ""
    status: str = ""
    metric: str = ""
    total_combinations: int = 0
    combinations_done: int = 0
    progress_pct: int = 0
    message: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
