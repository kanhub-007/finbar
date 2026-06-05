"""SqlEnrichmentArtifactRepository — SQLite-backed enrichment artifact store."""

import json
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from finbar.core.domain.entities.enrichment_job import EnrichmentJob
from finbar.infrastructure.tables.enrichment_artifact import (
    EnrichmentArtifact as OrmArtifact,
)


class SqlEnrichmentArtifactRepository:
    """Persist and retrieve enrichment artifacts from SQLite."""

    def __init__(self, db: Session):
        """Create the repository with a database session."""
        self._db = db

    def save(self, job: EnrichmentJob, bars: list[dict]) -> None:
        """Upsert an enrichment artifact."""
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
        orm = self._db.execute(
            select(OrmArtifact).where(OrmArtifact.job_id == job_id)
        ).scalar_one_or_none()
        if orm is None:
            return None
        return json.loads(orm.bars_json)

    def get_metadata(self, job_id: str) -> EnrichmentJob | None:
        """Return minimal job metadata from SQLite, or None if missing."""
        orm = self._db.execute(
            select(OrmArtifact).where(OrmArtifact.job_id == job_id)
        ).scalar_one_or_none()
        if orm is None:
            return None
        return EnrichmentJob(
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

    def delete(self, job_id: str) -> None:
        """Remove an artifact by job ID."""
        self._db.execute(delete(OrmArtifact).where(OrmArtifact.job_id == job_id))
        self._db.commit()

    def cleanup_expired(self, ttl_hours: int = 24) -> int:
        """Delete artifacts older than the TTL. Returns count deleted."""
        cutoff = datetime.now(UTC).isoformat()
        result = self._db.execute(
            delete(OrmArtifact).where(OrmArtifact.created_at < cutoff)
        )
        self._db.commit()
        return result.rowcount
