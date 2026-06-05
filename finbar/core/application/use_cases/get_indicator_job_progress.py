"""GetIndicatorJobProgressUseCase — query indicator job progress."""

from finbar.core.application.dto.indicator_job_progress_result import (
    IndicatorJobProgressResult,
)
from finbar.core.domain.entities.indicator_job import IndicatorJob
from finbar.core.domain.interfaces.indicator_job_manager import IndicatorJobManager


class GetIndicatorJobProgressUseCase:
    """Return current indicator job progress."""

    def __init__(self, manager: IndicatorJobManager):
        """Create the use case with an injected job manager."""
        self._manager = manager

    def execute(self, job_id: str) -> IndicatorJobProgressResult:
        """Return progress for a job ID."""
        job = self._manager.get(job_id)
        if job is None:
            return IndicatorJobProgressResult(found=False, job_id=job_id)
        return _result(job)


def _result(job: IndicatorJob) -> IndicatorJobProgressResult:
    return IndicatorJobProgressResult(
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
