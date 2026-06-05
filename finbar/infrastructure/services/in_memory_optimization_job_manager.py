"""InMemoryOptimizationJobManager — async optimization job storage."""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from finbar.core.domain.entities.optimization_job import OptimizationJob
from finbar.core.domain.interfaces.optimization_job_manager import (
    OptimizationJobManager,
)


class InMemoryOptimizationJobManager(OptimizationJobManager):
    """Thread-safe in-memory optimization job store."""

    def __init__(self, max_jobs: int = 50, ttl_seconds: int = 3600):
        """Initialize the in-memory optimization job store."""
        self._jobs: dict[str, OptimizationJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = threading.Lock()
        self._max_jobs = max(1, max_jobs)
        self._ttl = timedelta(seconds=max(1, ttl_seconds))

    def start(
        self,
        params: dict[str, Any],
        runner: Callable[[OptimizationJob], Awaitable[None]],
    ) -> OptimizationJob:
        """Create and start a background optimization job."""
        self.cleanup_expired()
        job = OptimizationJob(
            job_id=str(uuid.uuid4()),
            metric=params.get("metric", "sharpe_ratio"),
            metadata=dict(params),
        )
        task = asyncio.create_task(runner(job))
        with self._lock:
            self._jobs[job.job_id] = job
            self._tasks[job.job_id] = task
            self._enforce_max_jobs_locked()
        return job

    def get(self, job_id: str) -> OptimizationJob | None:
        """Return a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job: OptimizationJob, **updates: Any) -> None:
        """Update a job in-place."""
        with self._lock:
            for key, value in updates.items():
                setattr(job, key, value)

    def cancel(self, job_id: str) -> OptimizationJob | None:
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
        """Remove expired terminal jobs."""
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
