"""In-memory background fetch job manager.
Thread-safe dict of FetchJob instances with TTL cleanup and cancel support.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from finbar.presentation.mcp.fetch_job import FetchJob


class FetchJobManager:
    """Owns lifecycle and storage for in-memory MCP background fetch jobs."""

    def __init__(self, max_jobs: int = 50, ttl_seconds: int = 3600):
        self._jobs: dict[str, FetchJob] = {}
        self._lock = threading.Lock()
        self._max_jobs = max(1, max_jobs)
        self._ttl = timedelta(seconds=max(1, ttl_seconds))

    def start(
        self,
        params: dict[str, Any],
        runner: Callable[[FetchJob], Awaitable[None]],
    ) -> FetchJob:
        """Create and start a background job.

        Args:
            params: Dict with symbol, source, interval, start_date, end_date.
            runner: Async callable that performs the fetch and updates the job.

        Returns:
            The created FetchJob with status="queued".
        """
        self.cleanup_expired()
        job = FetchJob(
            job_id=str(uuid.uuid4()),
            symbol=params.get("symbol", ""),
            source=params.get("source", "yfinance"),
            interval=params.get("interval", "1d"),
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
        )
        task = asyncio.create_task(runner(job))
        job._task = task
        with self._lock:
            self._jobs[job.job_id] = job
            self._enforce_max_jobs_locked()
        return job

    def get(self, job_id: str) -> FetchJob | None:
        """Return a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job: FetchJob, **updates: Any) -> None:
        """Update a job in-place."""
        with self._lock:
            for key, value in updates.items():
                setattr(job, key, value)

    def cancel(self, job_id: str) -> FetchJob | None:
        """Cancel a queued or running job."""
        job = self.get(job_id)
        if not job:
            return None
        if job.status not in {"completed", "failed", "cancelled"}:
            if job._task:
                job._task.cancel()
            self.update(job, status="cancelled", error="Cancelled by user")
        return job

    def clear(self) -> None:
        """Cancel and remove all jobs. Intended for tests/cache resets."""
        with self._lock:
            jobs = list(self._jobs.values())
            self._jobs.clear()
        for job in jobs:
            if job._task and not job._task.done():
                job._task.cancel()

    def cleanup_expired(self) -> None:
        """Remove expired terminal jobs."""
        cutoff = datetime.now(UTC) - self._ttl
        with self._lock:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in {"completed", "failed", "cancelled"}
                and job._created_at < cutoff
            ]
            for job_id in expired:
                self._jobs.pop(job_id, None)

    def _enforce_max_jobs_locked(self) -> None:
        """Remove oldest terminal jobs if over limit."""
        if len(self._jobs) <= self._max_jobs:
            return
        removable = sorted(
            self._jobs.values(),
            key=lambda job: job._created_at,
        )
        for job in removable:
            if len(self._jobs) <= self._max_jobs:
                return
            if job.status in {"completed", "failed", "cancelled"}:
                self._jobs.pop(job.job_id, None)
