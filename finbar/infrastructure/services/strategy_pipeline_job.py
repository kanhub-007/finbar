"""StrategyPipelineJob — background strategy pipeline state tracker."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class StrategyPipelineJob:
    """Background strategy pipeline job state."""

    job_id: str
    status: str = "queued"
    symbol: str = ""
    source: str = ""
    start_date: str | None = None
    end_date: str | None = None
    enrichment_mode: str = "live_parity_streaming"
    progress_pct: int = 0
    stage: str = "queued"
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC), repr=False)
