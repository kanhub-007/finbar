"""CancelEnrichmentJobUseCase — cancel asynchronous enrichment work."""

from finbar.core.application.dto.enrichment_job_progress_result import (
    EnrichmentJobProgressResult,
)
from finbar.core.domain.entities.enrichment_job import EnrichmentJob
from finbar.core.domain.interfaces.enrichment_job_manager import EnrichmentJobManager


class CancelEnrichmentJobUseCase:
    """Cancel a queued or running enrichment job."""

    def __init__(self, manager: EnrichmentJobManager):
        """Create the use case with an injected job manager."""
        self._manager = manager

    def execute(self, job_id: str) -> EnrichmentJobProgressResult:
        """Cancel a job and return its updated state."""
        job = self._manager.cancel(job_id)
        if job is None:
            return EnrichmentJobProgressResult(found=False, job_id=job_id)
        return _result(job)


def _result(job: EnrichmentJob) -> EnrichmentJobProgressResult:
    return EnrichmentJobProgressResult(
        found=True,
        job_id=job.job_id,
        status=job.status,
        symbol=job.symbol,
        source=job.source,
        interval=job.interval,
        mode=job.mode,
        timeframe_alias=job.timeframe_alias,
        progress_pct=job.progress_pct,
        stage=job.stage,
        message=job.message,
        total_bar_count=job.total_bar_count,
        indicators_applied=list(job.indicators_applied),
        features_applied=list(job.features_applied),
        error=job.error,
        metadata=dict(job.metadata),
    )
