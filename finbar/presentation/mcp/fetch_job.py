"""FetchJob — background fetch job state tracker.

Dataclass shape adapted from kapsula/presentation/mcp/search_job.py:SearchJob.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class FetchJob:
    """Background fetch job state.

    Created when a client requests fresh data from a rate-limited source.
    The job runs in a background asyncio task; the client polls for
    progress and retrieves results when complete.
    """

    job_id: str
    status: str = "queued"
    symbol: str = ""
    source: str = ""
    interval: str = ""
    start_date: str | None = None
    end_date: str | None = None
    progress_pct: int = 0
    result: str | None = None
    error: str | None = None

    # Internal — managed by FetchJobManager
    _task: asyncio.Task | None = field(default=None, repr=False)
    _created_at: datetime = field(default_factory=lambda: datetime.now(UTC), repr=False)
