"""GetOptimizationJobProgressUseCase — query optimization job state."""

from finbar.core.application.dto.optimization_job_progress_result import (
    OptimizationJobProgressResult,
)
from finbar.core.domain.entities.optimization_job import OptimizationJob
from finbar.core.domain.interfaces.optimization_job_manager import (
    OptimizationJobManager,
)


class GetOptimizationJobProgressUseCase:
    """Return current optimization job progress."""

    def __init__(self, manager: OptimizationJobManager):
        """Create the use case with an injected job manager."""
        self._manager = manager

    def execute(self, job_id: str) -> OptimizationJobProgressResult:
        """Return progress for a job ID."""
        job = self._manager.get(job_id)
        if job is None:
            return OptimizationJobProgressResult(found=False, job_id=job_id)
        return _result(job)


def _result(job: OptimizationJob) -> OptimizationJobProgressResult:
    return OptimizationJobProgressResult(
        found=True,
        job_id=job.job_id,
        status=job.status,
        metric=job.metric,
        total_combinations=job.total_combinations,
        combinations_done=job.combinations_done,
        progress_pct=job.progress_pct,
        message=job.message,
        error=job.error,
        metadata=dict(job.metadata),
    )
