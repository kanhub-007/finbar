"""OptimizationJob entity for parameter sweep jobs."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from finbar.core.domain.entities.optimization_result import OptimizationResult


@dataclass
class OptimizationJob:
    """Background optimization job state."""

    job_id: str
    """Unique job identifier."""

    status: str = "queued"
    """Job status: queued, running, completed, failed, cancelled."""

    metric: str = "sharpe_ratio"
    """Metric used for ranking."""

    total_combinations: int = 0
    """Total param combinations to try."""

    combinations_done: int = 0
    """Number of combinations completed so far."""

    progress_pct: int = 0
    """Progress percentage from 0 to 100."""

    message: str = ""
    """Human-readable progress message."""

    results: list[OptimizationResult] = field(default_factory=list)
    """Ranked optimization results (populated on completion)."""

    error: str | None = None
    """Error message for failed jobs."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional machine-readable job metadata."""

    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    """Creation timestamp used for cleanup."""
