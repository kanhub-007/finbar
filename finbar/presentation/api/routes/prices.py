"""Price API endpoints — cached prices, fetch, delete."""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query

from finbar.core.application.dto.fetch_prices_request import FetchPricesRequest
from finbar.presentation.api.dto.requests import (
    FetchPricesRequest as ApiFetchRequest,
)
from finbar.presentation.api.dto.responses import (
    CachedPricesResponse,
    DeleteResponse,
    FetchJobResponse,
    PriceBarResponse,
)
from finbar.presentation.mcp.fetch_job import FetchJob
from finbar.presentation.mcp.tools._shared import (
    _get_db,
    _get_job_manager,
    _make_delete_cached_use_case,
    _make_fetch_prices_use_case,
    _make_get_latest_quote_use_case,
    _make_query_cached_use_case,
)

router = APIRouter(prefix="/api/prices", tags=["Prices"])


@router.get(
    "/latest/{symbol}",
    response_model=PriceBarResponse,
    summary="Get latest quote",
)
def get_latest(symbol: str, source: str = Query("yfinance")):
    """Get the most recent OHLCV bar for a symbol."""
    db = _get_db()
    try:
        use_case = _make_get_latest_quote_use_case(db, source)
        bar = use_case.execute(symbol.upper())
        if bar is None:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")
        return PriceBarResponse(
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
    finally:
        db.close()


@router.get(
    "/cached",
    response_model=CachedPricesResponse,
    summary="Query cached prices",
)
def get_cached(
    symbol: str = Query(...),
    source: str = Query("yfinance"),
    interval: str = Query("1d"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    """Query the local SQLite cache for previously-fetched OHLCV bars."""
    db = _get_db()
    try:
        use_case = _make_query_cached_use_case(db)
        result = use_case.execute(
            symbol=symbol.upper(),
            source=source,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
        )
        return CachedPricesResponse(
            symbol=result.symbol,
            source=result.source,
            interval=result.interval,
            bar_count=result.bar_count,
            bars=[
                PriceBarResponse(
                    timestamp=b.timestamp,
                    open=b.open,
                    high=b.high,
                    low=b.low,
                    close=b.close,
                    volume=b.volume,
                )
                for b in result.bars
            ],
        )
    finally:
        db.close()


@router.post(
    "/fetch",
    response_model=FetchJobResponse,
    summary="Start background price fetch",
)
async def fetch_prices(request: ApiFetchRequest):
    """Start a background fetch job. Returns job_id immediately."""
    manager = _get_job_manager()
    params = {
        "symbol": request.symbol.upper(),
        "source": request.source,
        "interval": request.interval,
        "start_date": request.start_date,
        "end_date": request.end_date,
    }
    job = manager.start(params, _run_fetch_job)
    return FetchJobResponse(
        job_id=job.job_id,
        symbol=job.symbol,
        source=job.source,
        interval=job.interval,
        status=job.status,
    )


@router.delete(
    "/cached",
    response_model=DeleteResponse,
    summary="Delete cached prices",
)
def delete_cached(
    symbol: str = Query(..., description="Ticker symbol (required)"),
    source: str | None = Query(None),
    interval: str | None = Query(None),
    before: str | None = Query(None, description="Delete bars before this date"),
):
    """Delete cached bars. Symbol is required."""
    db = _get_db()
    try:
        use_case = _make_delete_cached_use_case(db)
        deleted = use_case.execute(
            symbol=symbol.upper(),
            source=source,
            interval=interval,
            before_date=before,
        )
        return DeleteResponse(symbol=symbol.upper(), deleted_count=deleted)
    finally:
        db.close()


def _sync_run_fetch_job(job: FetchJob) -> None:
    """Synchronous fetch runner — runs in thread pool."""
    manager = _get_job_manager()
    manager.update(job, status="running", progress_pct=10)
    db = _get_db()
    try:
        use_case = _make_fetch_prices_use_case(db, job.source)
        request = FetchPricesRequest(
            symbol=job.symbol,
            source=job.source,
            interval=job.interval,
            start_date=job.start_date,
            end_date=job.end_date,
        )
        result = use_case.execute(request)
        if result.error:
            manager.update(job, status="failed", progress_pct=100, error=result.error)
            return
        manager.update(
            job,
            status="completed",
            progress_pct=100,
            result=json.dumps(
                {
                    "symbol": result.symbol,
                    "bar_count": result.bar_count,
                    "origin": result.origin,
                }
            ),
        )
    except Exception as exc:
        manager.update(job, status="failed", progress_pct=100, error=str(exc))
    finally:
        db.close()


async def _run_fetch_job(job: FetchJob) -> None:
    """Async wrapper — runs blocking fetch in thread pool."""
    try:
        await asyncio.to_thread(_sync_run_fetch_job, job)
    except asyncio.CancelledError:
        mgr = _get_job_manager()
        current = mgr.get(job.job_id)
        if current and current.status not in ("completed", "failed"):
            mgr.update(job, status="cancelled", error="Cancelled by user")
        raise
