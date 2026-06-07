"""GetOptimizationJobResultsUseCase — return ranked optimization results."""

from dataclasses import asdict

from finbar.core.application.dto.optimization_job_results_result import (
    OptimizationJobResultsResult,
)
from finbar.core.domain.interfaces.optimization_job_manager import (
    OptimizationJobManager,
)


class GetOptimizationJobResultsUseCase:
    """Return completed optimization job results."""

    def __init__(self, manager: OptimizationJobManager):
        """Create the use case with an injected job manager."""
        self._manager = manager

    def execute(self, job_id: str) -> OptimizationJobResultsResult:
        """Return ranked results for a completed optimization job."""
        job = self._manager.get(job_id)
        if job is None:
            return OptimizationJobResultsResult(found=False, job_id=job_id)
        if job.status != "completed":
            return OptimizationJobResultsResult(
                found=True,
                job_id=job_id,
                status=job.status,
                error=f"Job is not complete (status: {job.status})",
            )
        results = [asdict(r) for r in job.results]
        wf_result_raw = job.metadata.get("walk_forward_result")
        wf_result_dict = asdict(wf_result_raw) if wf_result_raw else None
        return OptimizationJobResultsResult(
            found=True,
            job_id=job_id,
            status=job.status,
            metric=job.metric,
            total_combinations=job.total_combinations,
            results=results,
            walk_forward_result=wf_result_dict,
        )
