"""SqlIndicatorArtifactRepository — SQLite-backed indicator artifact store."""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from finbar.core.domain.entities.indicator_job import IndicatorJob
from finbar.infrastructure.tables.indicator_artifact import (
    IndicatorArtifact as OrmArtifact,
)

_RETENTION_POLICY = "durable_until_deleted"


class SqlIndicatorArtifactRepository:
    """Persist and retrieve indicator artifacts from SQLite."""

    def __init__(self, db: Session):
        """Create the repository with a database session."""
        self._db = db

    def save(self, job: IndicatorJob, bars: list[dict]) -> None:
        """Upsert an indicator artifact."""
        bars_json = json.dumps(bars)
        indicators_json = json.dumps(job.indicators_applied)
        features_json = json.dumps(job.features_applied)
        created_at = datetime.now(UTC).isoformat()

        existing = self._db.execute(
            select(OrmArtifact).where(OrmArtifact.job_id == job.job_id)
        ).scalar_one_or_none()

        if existing:
            existing.bars_json = bars_json
            existing.total_bar_count = len(bars)
            existing.indicators_applied_json = indicators_json
            existing.features_applied_json = features_json
            existing.status = job.status
        else:
            self._db.add(
                OrmArtifact(
                    job_id=job.job_id,
                    symbol=job.symbol,
                    source=job.source,
                    interval=job.interval,
                    mode=job.mode,
                    timeframe_alias=job.timeframe_alias,
                    status=job.status,
                    bars_json=bars_json,
                    total_bar_count=len(bars),
                    indicators_applied_json=indicators_json,
                    features_applied_json=features_json,
                    created_at=created_at,
                )
            )
        self._db.commit()

    def get_bars(self, job_id: str) -> list[dict] | None:
        """Return all enriched bars for a job, or None if missing."""
        orm = self._get_orm(job_id)
        if orm is None:
            return None
        return _loads_bars(orm.bars_json)

    def get_metadata(self, job_id: str) -> IndicatorJob | None:
        """Return minimal job metadata from SQLite, or None if missing."""
        orm = self._get_orm(job_id)
        if orm is None:
            return None
        return IndicatorJob(
            job_id=orm.job_id,
            status=orm.status,
            symbol=orm.symbol,
            source=orm.source,
            interval=orm.interval,
            mode=orm.mode,
            timeframe_alias=orm.timeframe_alias,
            total_bar_count=orm.total_bar_count,
            indicators_applied=json.loads(orm.indicators_applied_json),
            features_applied=json.loads(orm.features_applied_json),
        )

    def list_metadata(
        self,
        symbol: str | None = None,
        source: str | None = None,
        interval: str | None = None,
    ) -> list[dict]:
        """Return artifact metadata records matching optional filters."""
        query = select(OrmArtifact)
        if symbol:
            query = query.where(OrmArtifact.symbol == symbol.upper())
        if source:
            query = query.where(OrmArtifact.source == source)
        if interval:
            query = query.where(OrmArtifact.interval == interval)
        rows = self._db.execute(query.order_by(OrmArtifact.created_at.desc())).scalars()
        return [_metadata_from_orm(row, include_null_counts=False) for row in rows]

    def describe(self, job_id: str) -> dict | None:
        """Return detailed metadata for one artifact without returning bars."""
        orm = self._get_orm(job_id)
        if orm is None:
            return None
        return _metadata_from_orm(orm, include_null_counts=True)

    def query_bars(
        self,
        job_id: str,
        columns: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 0,
        page_size: int = 500,
    ) -> tuple[list[dict], int, int, int, int, list[str]]:
        """Return a filtered and paginated page of artifact bars."""
        bars = self.get_bars(job_id)
        if bars is None:
            raise KeyError(job_id)
        return _page_bars(bars, columns, start_date, end_date, page, page_size)

    def delete(self, job_id: str) -> bool:
        """Remove an artifact by job ID. Return True when a row was deleted."""
        result = self._db.execute(
            delete(OrmArtifact).where(OrmArtifact.job_id == job_id)
        )
        self._db.commit()
        return bool(result.rowcount)

    def cleanup_expired(self, ttl_hours: int = 24) -> int:
        """Delete artifacts older than the TTL. Returns count deleted."""
        cutoff = datetime.now(UTC) - timedelta(hours=max(1, ttl_hours))
        result = self._db.execute(
            delete(OrmArtifact).where(OrmArtifact.created_at < cutoff.isoformat())
        )
        self._db.commit()
        return result.rowcount

    def _get_orm(self, job_id: str) -> OrmArtifact | None:
        """Return the ORM row for an artifact ID."""
        return self._db.execute(
            select(OrmArtifact).where(OrmArtifact.job_id == job_id)
        ).scalar_one_or_none()


def _loads_bars(raw: str) -> list[dict]:
    """Load artifact bars from JSON."""
    value = json.loads(raw)
    return value if isinstance(value, list) else []


def _metadata_from_orm(orm: OrmArtifact, include_null_counts: bool) -> dict:
    """Build compact artifact metadata from an ORM row."""
    bars = _loads_bars(orm.bars_json)
    columns = _columns_from_bars(bars)
    start_date, end_date = _date_range(bars)
    return {
        "artifact_id": orm.job_id,
        "symbol": orm.symbol,
        "source": orm.source,
        "interval": orm.interval,
        "mode": orm.mode,
        "timeframe_alias": orm.timeframe_alias,
        "status": orm.status,
        "bar_count": orm.total_bar_count,
        "start_date": start_date,
        "end_date": end_date,
        "columns": columns,
        "indicators_applied": json.loads(orm.indicators_applied_json),
        "features_applied": json.loads(orm.features_applied_json),
        "null_counts": _null_counts(bars, columns) if include_null_counts else {},
        "created_at": orm.created_at,
        "expires_at": None,
        "retention_policy": _RETENTION_POLICY,
    }


def _columns_from_bars(bars: list[dict]) -> list[str]:
    """Return stable column order from the first occurrence in bars."""
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
