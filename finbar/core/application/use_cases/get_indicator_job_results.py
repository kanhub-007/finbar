"""GetIndicatorJobResultsUseCase — page completed indicator artifacts."""

from finbar.core.application.dto.indicator_job_results_result import (
    IndicatorJobResultsResult,
)
from finbar.core.domain.interfaces.indicator_job_manager import IndicatorJobManager


class GetIndicatorJobResultsUseCase:
    """Return paginated results for completed indicator jobs."""

    def __init__(self, manager: IndicatorJobManager):
        """Create the use case with an injected job manager."""
        self._manager = manager

    def execute(
        self,
        job_id: str,
        page: int = 0,
        page_size: int = 500,
    ) -> IndicatorJobResultsResult:
        """Return a page of enriched bars for a completed job."""
        job = self._manager.get(job_id)
        if job is None:
            return IndicatorJobResultsResult(found=False, job_id=job_id)
        if job.status != "completed":
            return IndicatorJobResultsResult(
                found=True,
                job_id=job_id,
                status=job.status,
                error=f"Job is not complete (status: {job.status})",
            )
        bars, page, page_size, total_pages = self._manager.get_result_page(
            job_id, page, page_size
        )
        return IndicatorJobResultsResult(
            found=True,
            job_id=job_id,
            status=job.status,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            total_bar_count=job.total_bar_count,
            bar_count=len(bars),
            bars=bars,
        )
