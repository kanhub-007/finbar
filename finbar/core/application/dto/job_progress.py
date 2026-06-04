"""JobProgress DTO — background fetch job status."""

from dataclasses import dataclass


@dataclass(frozen=True)
class JobProgress:
    """Snapshot of a background fetch job's current state."""

    job_id: str
    status: str
    symbol: str
    source: str
    interval: str
    progress_pct: int = 0
    bar_count: int = 0
    error: str | None = None
