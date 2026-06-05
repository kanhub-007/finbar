"""FetchJob — background fetch job state tracker."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class FetchJob:
    """Background fetch job state for asynchronous price fetches."""

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
    task: asyncio.Task | None = field(default=None, repr=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC), repr=False)
