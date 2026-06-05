"""Optimization API endpoints — parameter sweep / grid search."""

import logging

from fastapi import APIRouter, HTTPException

from finbar.core.application.dto.start_optimization_job_request import (
    StartOptimizationJobRequest,
)
from finbar.startup.service_factory import (
    _make_cancel_optimization_job_use_case,
    _make_get_optimization_job_progress_use_case,
    _make_get_optimization_job_results_use_case,
    _make_start_optimization_job_use_case,
)

_SUPPORTED_METRICS = frozenset(
    {
        "sharpe_ratio",
        "sortino_ratio",
        "total_return",
        "profit_factor",
        "win_rate",
        "calmar_ratio",
    }
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/optimization", tags=["Optimization"])


@router.post("/jobs", summary="Start an optimization job")
async def start_optimization_job(
    definition: str,
    bars_artifact_id: str,
    param_ranges: dict[str, dict[str, float]],
    metric: str = "sharpe_ratio",
    informative_bars_artifact_ids: dict[str, str] | None = None,
    initial_cash: float = 10000.0,
    search_method: str = "grid",
    random_count: int = 20,
):
    """Start a grid or random search optimization job."""
    if metric not in _SUPPORTED_METRICS:
        raise HTTPException(status_code=400, detail=f"Invalid metric: {metric}")
    for name, spec in param_ranges.items():
        if not all(k in spec for k in ("min", "max")):
            raise HTTPException(
                status_code=400,
                detail=f"Parameter '{name}' must have min and max",
            )
    job = _make_start_optimization_job_use_case().execute(
        StartOptimizationJobRequest(
            definition=definition,
            bars_artifact_id=bars_artifact_id,
            param_ranges=param_ranges,
            metric=metric,
            informative_bars_artifact_ids=informative_bars_artifact_ids or {},
            initial_cash=initial_cash,
            search_method=search_method,
            random_count=random_count,
        )
    )
    return {
        "job_id": job.job_id,
        "status": job.status,
        "metric": job.metric,
    }


@router.get("/jobs/{job_id}", summary="Get optimization job progress")
def get_optimization_job_progress(job_id: str):
    """Return current optimization job progress."""
    result = _make_get_optimization_job_progress_use_case().execute(job_id)
    if not result.found:
        raise HTTPException(status_code=404, detail="Job not found")
    return result.__dict__


@router.get("/jobs/{job_id}/results", summary="Get optimization results")
def get_optimization_job_results(job_id: str):
    """Return ranked optimization results from a completed job."""
    result = _make_get_optimization_job_results_use_case().execute(job_id)
    if not result.found:
        raise HTTPException(status_code=404, detail="Job not found")
    if result.error:
        raise HTTPException(status_code=400, detail=result.error)
    return result.__dict__


@router.delete("/jobs/{job_id}", summary="Cancel optimization job")
def cancel_optimization_job(job_id: str):
    """Cancel a queued or running optimization job."""
    result = _make_cancel_optimization_job_use_case().execute(job_id)
    if not result.found:
        raise HTTPException(status_code=404, detail="Job not found")
    return result.__dict__
