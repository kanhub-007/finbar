"""Job API endpoints — status, results, cancel."""

from fastapi import APIRouter, HTTPException

from finbar.presentation.api.dto.responses import JobStatusResponse
from finbar.startup.service_factory import _get_job_manager

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
)
def get_job(job_id: str):
    """Check the status of a background fetch job."""
    manager = _get_job_manager()
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return JobStatusResponse(
        job_id=job.job_id,
        symbol=job.symbol,
        source=job.source,
        interval=job.interval,
        status=job.status,
        progress_pct=job.progress_pct,
        error=job.error,
    )


@router.get(
    "/{job_id}/results",
    summary="Get job results",
)
def get_job_results(job_id: str):
    """Retrieve results of a completed background fetch job."""
    manager = _get_job_manager()
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if job.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Job not complete (status: {job.status})",
        )
    return {"job_id": job.job_id, "result": job.result}


@router.delete(
    "/{job_id}",
    summary="Cancel job",
)
def cancel_job(job_id: str):
    """Cancel a running or queued background fetch job."""
    manager = _get_job_manager()
    job = manager.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return {"job_id": job_id, "status": "cancelled"}
