"""Indicator API endpoints — async server-side indicator/feature jobs."""

import logging

from fastapi import APIRouter, HTTPException

from finbar.core.application.dto.start_indicator_job_request import (
    StartIndicatorJobRequest,
)
from finbar.startup.service_factory import (
    _make_cancel_indicator_job_use_case,
    _make_get_indicator_job_progress_use_case,
    _make_get_indicator_job_results_use_case,
    _make_start_indicator_job_use_case,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/indicators", tags=["Indicators"])


@router.post("/jobs", summary="Start an indicator job")
async def start_indicator_job(
    symbol: str,
    source: str = "yfinance",
    interval: str = "1d",
    mode: str = "selected",
    indicators: list[str] | None = None,
    definition: str | None = None,
    params: dict | None = None,
    timeframe_alias: str = "primary",
    start_date: str | None = None,
    end_date: str | None = None,
):
    """Start a background indicator job using cached bars."""
    if mode not in ("selected", "strategy_required"):
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}")
    job = _make_start_indicator_job_use_case().execute(
        StartIndicatorJobRequest(
            symbol=symbol.upper(),
            source=source,
            interval=interval,
            mode=mode,
            indicators=indicators or [],
            definition=definition,
            params=params or {},
            timeframe_alias=timeframe_alias,
            start_date=start_date,
            end_date=end_date,
        )
    )
    return {
        "job_id": job.job_id,
        "status": job.status,
        "symbol": job.symbol,
        "source": job.source,
        "interval": job.interval,
        "mode": job.mode,
        "timeframe_alias": job.timeframe_alias,
    }


@router.get("/jobs/{job_id}", summary="Get indicator job progress")
def get_indicator_job_progress(job_id: str):
    """Return current indicator job status and progress."""
    result = _make_get_indicator_job_progress_use_case().execute(job_id)
    if not result.found:
        raise HTTPException(status_code=404, detail="Job not found")
    return result.__dict__


@router.get("/jobs/{job_id}/results", summary="Get indicator job results")
def get_indicator_job_results(job_id: str, page: int = 0, page_size: int = 500):
    """Return paginated enriched bars from a completed indicator job."""
    result = _make_get_indicator_job_results_use_case().execute(
        job_id, page, page_size
    )
    if not result.found:
        raise HTTPException(status_code=404, detail="Job not found")
    if result.error:
        raise HTTPException(status_code=400, detail=result.error)
    return result.__dict__


@router.delete("/jobs/{job_id}", summary="Cancel indicator job")
def cancel_indicator_job(job_id: str):
    """Cancel a queued or running indicator job."""
    result = _make_cancel_indicator_job_use_case().execute(job_id)
    if not result.found:
        raise HTTPException(status_code=404, detail="Job not found")
    return result.__dict__
