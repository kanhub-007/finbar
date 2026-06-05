"""InMemoryEnrichmentJobManager — async enrichment job storage."""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from finbar.core.domain.entities.enrichment_job import EnrichmentJob
from finbar.core.domain.interfaces.enrichment_job_manager import EnrichmentJobManager


class InMemoryEnrichmentJobManager(EnrichmentJobManager):
    """Thread-safe in-memory enrichment job and artifact store."""

    def __init__(self, max_jobs: int = 50, ttl_seconds: int = 3600):
        """Initialize the in-memory enrichment job store."""
        self._jobs: dict[str, EnrichmentJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._results: dict[str, list[dict]] = {}
        self._lock = threading.Lock()
        self._max_jobs = max(1, max_jobs)
        self._ttl = timedelta(seconds=max(1, ttl_seconds))

    def start(
        self,
        params: dict[str, Any],
        runner: Callable[[EnrichmentJob], Awaitable[None]],
    ) -> EnrichmentJob:
        """Create and start a background enrichment job."""
        self.cleanup_expired()
        job = EnrichmentJob(
            job_id=str(uuid.uuid4()),
            symbol=params.get("symbol", ""),
            source=params.get("source", "yfinance"),
            interval=params.get("interval", "1d"),
            mode=params.get("mode", "selected"),
            timeframe_alias=params.get("timeframe_alias", "primary"),
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
            metadata=dict(params),
        )
        task = asyncio.create_task(runner(job))
        with self._lock:
            self._jobs[job.job_id] = job
            self._tasks[job.job_id] = task
            self._enforce_max_jobs_locked()
        return job

    def get(self, job_id: str) -> EnrichmentJob | None:
        """Return a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job: EnrichmentJob, **updates: Any) -> None:
        """Update a job in-place."""
        with self._lock:
            for key, value in updates.items():
                setattr(job, key, value)

    def store_result(self, job: EnrichmentJob, bars: list[dict]) -> None:
        """Store enriched bars for a completed job."""
        with self._lock:
            self._results[job.job_id] = list(bars)
            job.total_bar_count = len(bars)

    def get_result_page(
        self,
        job_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int, int, int]:
        """Return bars plus page metadata: bars, page, page_size, total_pages."""
        with self._lock:
            bars = list(self._results.get(job_id, []))
        total = len(bars)
        page_size = max(1, min(page_size, 1000))
        total_pages = (total + page_size - 1) // page_size if total else 0
        page = max(0, min(page, total_pages - 1)) if total_pages else 0
        start = page * page_size
        end = min(start + page_size, total)
        return bars[start:end], page, page_size, total_pages

    def cancel(self, job_id: str) -> EnrichmentJob | None:
        """Cancel a queued or running job."""
        job = self.get(job_id)
        if job is None:
            return None
        if job.status not in {"completed", "failed", "cancelled"}:
            task = self._tasks.get(job_id)
            if task:
                task.cancel()
            self.update(job, status="cancelled", error="Cancelled by user")
        return job

    def cleanup_expired(self) -> None:
        """Remove expired terminal jobs and results."""
        cutoff = datetime.now(UTC) - self._ttl
        with self._lock:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in {"completed", "failed", "cancelled"}
                and job.created_at < cutoff
            ]
            for job_id in expired:
                self._jobs.pop(job_id, None)
                self._tasks.pop(job_id, None)
                self._results.pop(job_id, None)

    def _enforce_max_jobs_locked(self) -> None:
        if len(self._jobs) <= self._max_jobs:
            return
        removable = sorted(self._jobs.values(), key=lambda job: job.created_at)
        for job in removable:
            if len(self._jobs) <= self._max_jobs:
                return
            if job.status in {"completed", "failed", "cancelled"}:
                self._jobs.pop(job.job_id, None)
                self._tasks.pop(job.job_id, None)
                self._results.pop(job.job_id, None)
