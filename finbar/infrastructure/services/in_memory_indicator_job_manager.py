"""InMemoryIndicatorJobManager — async indicator job storage."""

from __future__ import annotations

import asyncio
import pickle
import threading
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from finbar.core.domain.entities.indicator_job import IndicatorJob
from finbar.core.domain.interfaces.indicator_artifact_provider import (
    IndicatorArtifactProvider,
)
from finbar.core.domain.interfaces.indicator_job_manager import IndicatorJobManager
from finbar.infrastructure.repositories.sql_indicator_artifact_repository import (
    SqlIndicatorArtifactRepository,
)

_RETENTION_POLICY = "durable_until_deleted"


class InMemoryIndicatorJobManager(IndicatorJobManager, IndicatorArtifactProvider):
    """Thread-safe in-memory indicator job and artifact store.

    Artifacts are persisted to SQLite for restart survival. In-memory storage
    provides the fast path during a live session and is safe to evict.
    """

    def __init__(
        self,
        max_jobs: int = 50,
        ttl_seconds: int = 3600,
        session_factory: Callable[[], Session] | None = None,
    ):
        """Initialize the in-memory indicator job store."""
        self._session_factory = session_factory
        self._jobs: dict[str, IndicatorJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._results: dict[str, list[dict]] = {}
        self._frames: dict[str, bytes] = {}
        self._lock = threading.Lock()
        self._max_jobs = max(1, max_jobs)
        self._ttl = timedelta(seconds=max(1, ttl_seconds))

    def start(
        self,
        params: dict[str, Any],
        runner: Callable[[IndicatorJob], Awaitable[None]],
    ) -> IndicatorJob:
        """Create and start a background indicator job."""
        self.cleanup_expired()
        job = IndicatorJob(
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

    def get(self, job_id: str) -> IndicatorJob | None:
        """Return a job by ID, falling back to persisted metadata."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            return job
        return self._load_metadata_from_sql(job_id)

    def update(self, job: IndicatorJob, **updates: Any) -> None:
        """Update a job in-place."""
        with self._lock:
            for key, value in updates.items():
                setattr(job, key, value)

    def store_result(self, job: IndicatorJob, bars: list[dict]) -> None:
        """Store enriched bars in-memory and persist to SQLite."""
        with self._lock:
            self._results[job.job_id] = list(bars)
            job.total_bar_count = len(bars)
        self._persist_artifact(job, bars)

    def store_frame(self, job: IndicatorJob, frame: Any) -> None:
        """Cache a pickled DataFrame for hot-path backtest access."""
        with self._lock:
            self._frames[job.job_id] = pickle.dumps(frame)

    def get_artifact_job(self, job_id: str) -> IndicatorJob | None:
        """Return metadata for an indicator artifact job."""
        return self.get(job_id)

    def get_artifact_bars(self, job_id: str) -> list[dict] | None:
        """Return all bars for an indicator artifact."""
        with self._lock:
            bars = self._results.get(job_id)
            if bars is not None:
                return list(bars)
        return self._load_bars_from_sql(job_id)

    def get_artifact_frame(self, job_id: str) -> Any:
        """Return a cached DataFrame or None if not available."""
        with self._lock:
            data = self._frames.get(job_id)
            return pickle.loads(data) if data is not None else None

    def list_artifacts(
        self,
        symbol: str | None = None,
        source: str | None = None,
        interval: str | None = None,
    ) -> list[dict]:
        """Return artifact metadata matching optional filters."""
        if self._session_factory is not None:
            return self._with_repo(
                lambda repo: repo.list_metadata(symbol, source, interval)
            )
        return self._list_memory_artifacts(symbol, source, interval)

    def describe_artifact(self, job_id: str) -> dict | None:
        """Return detailed artifact metadata without returning bars."""
        if self._session_factory is not None:
            return self._with_repo(lambda repo: repo.describe(job_id))
        job = self.get_artifact_job(job_id)
        bars = self.get_artifact_bars(job_id)
        if job is None or bars is None:
            return None
        return _metadata_from_job(job, bars, include_null_counts=True)

    def query_artifact_bars(
        self,
        job_id: str,
        columns: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 0,
        page_size: int = 500,
    ) -> tuple[list[dict], int, int, int, int, list[str]]:
        """Return a filtered page of artifact bars."""
        if self._session_factory is not None:
            return self._with_repo(
                lambda repo: repo.query_bars(
                    job_id,
                    columns,
                    start_date,
                    end_date,
                    page,
                    page_size,
                )
            )
        bars = self.get_artifact_bars(job_id)
        if bars is None:
            raise KeyError(job_id)
        return _page_bars(bars, columns, start_date, end_date, page, page_size)

    def delete_artifact(self, job_id: str) -> bool:
        """Delete an artifact explicitly from memory and persistence."""
        with self._lock:
            existed_memory = job_id in self._results or job_id in self._jobs
            self._jobs.pop(job_id, None)
            self._tasks.pop(job_id, None)
            self._results.pop(job_id, None)
            self._frames.pop(job_id, None)
        existed_sql = False
        if self._session_factory is not None:
            existed_sql = self._with_repo(lambda repo: repo.delete(job_id))
        return existed_memory or existed_sql

    def get_result_page(
        self,
        job_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int, int, int]:
        """Return bars plus page metadata: bars, page, page_size, total_pages."""
        with self._lock:
            bars = list(self._results.get(job_id, []))
        if not bars:
            sql_bars = self._load_bars_from_sql(job_id)
            if sql_bars:
                bars = sql_bars
        page_bars, page, page_size, total_pages, _total, _columns = _page_bars(
            bars,
            None,
            None,
            None,
            page,
            page_size,
        )
        return page_bars, page, page_size, total_pages

    def cancel(self, job_id: str) -> IndicatorJob | None:
        """Cancel a queued or running job."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.status not in {"completed", "failed", "cancelled"}:
            task = self._tasks.get(job_id)
            if task:
                task.cancel()
            self.update(job, status="cancelled", error="Cancelled by user")
        return job

    def cleanup_expired(self) -> None:
        """Remove expired in-memory terminal jobs and hot-cache results."""
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
                self._frames.pop(job_id, None)

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

    def _persist_artifact(self, job: IndicatorJob, bars: list[dict]) -> None:
        if self._session_factory is None:
            return
        self._with_repo(lambda repo: repo.save(job, bars))

    def _load_bars_from_sql(self, job_id: str) -> list[dict] | None:
        if self._session_factory is None:
            return None
        return self._with_repo(lambda repo: repo.get_bars(job_id))

    def _load_metadata_from_sql(self, job_id: str) -> IndicatorJob | None:
        if self._session_factory is None:
            return None
        return self._with_repo(lambda repo: repo.get_metadata(job_id))

    def _list_memory_artifacts(
        self,
        symbol: str | None,
        source: str | None,
        interval: str | None,
    ) -> list[dict]:
        """Return artifact metadata from memory when persistence is unavailable."""
        with self._lock:
            jobs = list(self._jobs.values())
        items = []
        for job in jobs:
            bars = self.get_artifact_bars(job.job_id)
            if bars is None or not _matches(job, symbol, source, interval):
                continue
            items.append(_metadata_from_job(job, bars, include_null_counts=False))
        return items

    def _with_repo(self, callback):
        """Run a callback against a short-lived artifact repository."""
        db = self._session_factory()
        try:
            return callback(SqlIndicatorArtifactRepository(db))
        finally:
            db.close()


def _matches(
    job: IndicatorJob,
    symbol: str | None,
    source: str | None,
    interval: str | None,
) -> bool:
    """Return True when a job matches optional metadata filters."""
    if symbol and job.symbol != symbol.upper():
        return False
    if source and job.source != source:
        return False
    if interval and job.interval != interval:
        return False
    return True


def _metadata_from_job(
    job: IndicatorJob,
    bars: list[dict],
    include_null_counts: bool,
) -> dict:
    """Build compact artifact metadata from an in-memory job and bars."""
    columns = _columns_from_bars(bars)
    start_date, end_date = _date_range(bars)
    return {
        "artifact_id": job.job_id,
        "symbol": job.symbol,
        "source": job.source,
        "interval": job.interval,
        "mode": job.mode,
        "timeframe_alias": job.timeframe_alias,
        "status": job.status,
        "bar_count": len(bars),
        "start_date": start_date,
        "end_date": end_date,
        "columns": columns,
        "indicators_applied": list(job.indicators_applied),
        "features_applied": list(job.features_applied),
        "null_counts": _null_counts(bars, columns) if include_null_counts else {},
        "created_at": job.created_at.isoformat(),
        "expires_at": None,
        "retention_policy": _RETENTION_POLICY,
    }


def _columns_from_bars(bars: list[dict]) -> list[str]:
    """Return stable column order from bars."""
    columns: list[str] = []
    seen: set[str] = set()
    for bar in bars:
        for key in bar:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    return columns


def _date_range(bars: list[dict]) -> tuple[str, str]:
    """Return first and last timestamp strings from bars."""
    if not bars:
        return "", ""
    return str(bars[0].get("timestamp", "")), str(bars[-1].get("timestamp", ""))


def _null_counts(bars: list[dict], columns: list[str]) -> dict[str, int]:
    """Count null or missing values by column."""
    return {
        column: sum(1 for bar in bars if bar.get(column) is None) for column in columns
    }


def _page_bars(
    bars: list[dict],
    columns: list[str] | None,
    start_date: str | None,
    end_date: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict], int, int, int, int, list[str]]:
    """Filter, project, and paginate artifact bars."""
    filtered = _filter_bars(bars, start_date, end_date)
    selected_columns = columns or _columns_from_bars(filtered)
    projected = [_project_bar(bar, selected_columns) for bar in filtered]
    total = len(projected)
    page_size = max(1, min(page_size, 1000))
    total_pages = (total + page_size - 1) // page_size if total else 0
    page = max(0, min(page, total_pages - 1)) if total_pages else 0
    start = page * page_size
    end = min(start + page_size, total)
    return projected[start:end], page, page_size, total_pages, total, selected_columns


def _filter_bars(
    bars: list[dict],
    start_date: str | None,
    end_date: str | None,
) -> list[dict]:
    """Filter bars by timestamp string range."""
    filtered = []
    for bar in bars:
        timestamp = str(bar.get("timestamp", ""))
        if start_date and timestamp < start_date:
            continue
        if end_date and timestamp > end_date:
            continue
        filtered.append(bar)
    return filtered


def _project_bar(bar: dict, columns: list[str]) -> dict:
    """Return a bar with only requested columns."""
    return {column: bar.get(column) for column in columns}
