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

    _MAX_CONCURRENT_JOBS = 3

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
        # Lightweight metadata cache: columns + dates computed once at
        # store time so listing doesn't load all bars.
        self._meta_cache: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._max_jobs = max(1, max_jobs)
        self._ttl = timedelta(seconds=max(1, ttl_seconds))
        # Semaphore limits concurrent indicator jobs to prevent
        # memory/CPU exhaustion from unbounded parallel computation.
        self._semaphore = asyncio.Semaphore(self._MAX_CONCURRENT_JOBS)

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

        # Wrap the runner with the concurrency semaphore so at most
        # _MAX_CONCURRENT_JOBS run in parallel.
        async def _gated_runner(j: IndicatorJob) -> None:
            async with self._semaphore:
                await runner(j)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop (e.g. synchronous caller).
            # Dispatch the job on a fresh daemon thread with its own loop.
            thread = threading.Thread(
                target=lambda: asyncio.run(_gated_runner(job)),
                daemon=True,
            )
            thread.start()
        else:
            task = loop.create_task(_gated_runner(job))
            with self._lock:
                self._tasks[job.job_id] = task
        with self._lock:
            self._jobs[job.job_id] = job
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
        # Pre-compute lightweight metadata (columns, dates) ONCE so
        # list/describe never need to load all bars.
        meta = _compute_lightweight_meta(bars)
        with self._lock:
            self._results[job.job_id] = list(bars)
            self._meta_cache[job.job_id] = meta
            job.total_bar_count = len(bars)
        content_hash = job.metadata.get("content_hash", "")
        self._persist_artifact(job, bars, content_hash)

    def store_frame(self, job: IndicatorJob, frame: Any) -> None:
        """Cache a pickled DataFrame for hot-path backtest access.

        Serialization happens OUTSIDE the lock so other threads accessing the
        manager (progress polls, result reads) are not blocked for the full
        pickle duration.
        """
        data = pickle.dumps(frame)
        with self._lock:
            self._frames[job.job_id] = data

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
        """Return a cached DataFrame or None if not available.

        Deserialization happens OUTSIDE the lock so other threads are not
        blocked for the full unpickle duration.
        """
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
        if job is None:
            return None
        # Use cached lightweight metadata when available to avoid
        # loading all bars just for column names and dates.
        with self._lock:
            meta = self._meta_cache.get(job_id)
        if meta is not None:
            return _metadata_from_cache(job, meta, include_null_counts=False)
        bars = self.get_artifact_bars(job_id)
        if bars is None:
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
            self._meta_cache.pop(job_id, None)
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
                self._meta_cache.pop(job_id, None)

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
                self._meta_cache.pop(job.job_id, None)

    def _persist_artifact(
        self, job: IndicatorJob, bars: list[dict], content_hash: str = ""
    ) -> None:
        if self._session_factory is None:
            return
        self._with_repo(lambda repo: repo.save(job, bars, content_hash))

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
        """Return artifact metadata from memory when persistence is unavailable.

        Uses the cached lightweight metadata (columns, dates) computed at
        store time. Does NOT load the full bars list.
        """
        with self._lock:
            jobs = list(self._jobs.values())
            meta_snapshot = {jid: dict(m) for jid, m in self._meta_cache.items()}
        items = []
        for job in jobs:
            if not _matches(job, symbol, source, interval):
                continue
            meta = meta_snapshot.get(job.job_id)
            if meta is None:
                # Fallback: bars not yet cached (job may still be running)
                bars = self.get_artifact_bars(job.job_id)
                if bars is None:
                    continue
                items.append(_metadata_from_job(job, bars, include_null_counts=False))
            else:
                items.append(_metadata_from_cache(job, meta, include_null_counts=False))
        return items

    def _with_repo(self, callback):
        """Run a callback against a short-lived artifact repository."""
        db = self._session_factory()
        try:
            return callback(SqlIndicatorArtifactRepository(db))
        finally:
            db.close()


def _compute_lightweight_meta(bars: list[dict]) -> dict:
    """Compute columns + date range + null counts from bars in ONE pass.

    Called once at store time so list/describe avoid loading all bars.
    Null counts are pre-computed here so ``_metadata_from_cache`` can
    serve them without a separate O(n * cols) scan.
    """
    if not bars:
        return {
            "columns": [],
            "start_date": "",
            "end_date": "",
            "bar_count": 0,
            "null_counts": {},
        }
    # Single-pass column discovery + null counting.
    columns: list[str] = []
    seen: set[str] = set()
    nulls: dict[str, int] = {}
    for bar in bars:
        for key in bar:
            if key not in seen:
                seen.add(key)
                columns.append(key)
                nulls[key] = 0
            if bar.get(key) is None:
                nulls[key] += 1
    return {
        "columns": columns,
        "start_date": str(bars[0].get("timestamp", "")),
        "end_date": str(bars[-1].get("timestamp", "")),
        "bar_count": len(bars),
        "null_counts": nulls,
    }


def _metadata_from_cache(
    job: IndicatorJob,
    meta: dict,
    include_null_counts: bool,
) -> dict:
    """Build artifact metadata from the cached lightweight dict.

    Null counts are pre-computed at store time (see
    ``_compute_lightweight_meta``) and served from the cache so
    ``describe_artifact`` never loads all bars.
    """
    return {
        "artifact_id": job.job_id,
        "symbol": job.symbol,
        "source": job.source,
        "interval": job.interval,
        "mode": job.mode,
        "timeframe_alias": job.timeframe_alias,
        "status": job.status,
        "bar_count": meta.get("bar_count", job.total_bar_count),
        "start_date": meta.get("start_date", ""),
        "end_date": meta.get("end_date", ""),
        "columns": meta.get("columns", []),
        "indicators_applied": list(job.indicators_applied),
        "features_applied": list(job.features_applied),
        "null_counts": meta.get("null_counts", {}) if include_null_counts else {},
        "created_at": job.created_at.isoformat(),
        "expires_at": None,
        "retention_policy": _RETENTION_POLICY,
    }


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
    """Filter, project, and paginate artifact bars.

    Counts matching bars and collects only the requested page slice in a
    single pass.  The previous implementation materialised a full filtered
    list (up to all bars) even when only ``page_size`` rows were returned.
    """
    page_size = max(1, min(page_size, 1000))
    start_idx = page * page_size
    end_idx = start_idx + page_size
    # Resolve column set — prefer the caller's list, then cached metadata,
    # falling back to scanning the first bar as a cheap heuristic.
    selected_columns: list[str] | None = None
    if columns:
        selected_columns = list(columns)

    projected: list[dict] = []
    total = 0
    for bar in bars:
        timestamp = str(bar.get("timestamp", ""))
        if start_date and timestamp < start_date:
            continue
        if end_date and timestamp > end_date:
            continue
        # Discover columns lazily from the first matching bar when caller
        # didn't specify them (avoids _columns_from_bars scanning all bars).
        if selected_columns is None:
            selected_columns = list(bar.keys())
        if total >= start_idx and total < end_idx:
            projected.append(_project_bar(bar, selected_columns))
        total += 1

    if selected_columns is None:
        selected_columns = []
    total_pages = (total + page_size - 1) // page_size if total else 0
    page = max(0, min(page, total_pages - 1)) if total_pages else 0
    return projected, page, page_size, total_pages, total, selected_columns


def _filter_bars(
    bars: list[dict],
    start_date: str | None,
    end_date: str | None,
) -> list[dict]:
    """Filter bars by timestamp string range.

    .. deprecated::
        Retained for backward compatibility.  ``_page_bars`` now does a
        single-pass count-and-collect that avoids materialising the full
        filtered list.
    """
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
