"""MCP price tools — cached query, latest quote, delete, fresh fetch."""

import asyncio
import json

from fastmcp import FastMCP

from finbar.core.application.dto.fetch_prices_request import FetchPricesRequest
from finbar.core.domain.entities.price_bar import PriceBar
from finbar.presentation.mcp.fetch_job import FetchJob

from ._shared import (
    _get_db,
    _get_job_manager,
    _make_delete_cached_use_case,
    _make_fetch_prices_use_case,
    _make_get_latest_quote_use_case,
    _make_query_cached_use_case,
)


def register_price_tools(mcp: FastMCP) -> None:
    """Register all price-related MCP tools."""

    @mcp.tool(
        name="get_latest_quote",
        description=(
            "Get the most recent OHLCV bar for a symbol. "
            "Quick single-point fetch — returns immediately. "
            "Source defaults to 'yfinance'."
        ),
    )
    def get_latest_quote(symbol: str, source: str = "yfinance") -> str:
        db = _get_db()
        try:
            use_case = _make_get_latest_quote_use_case(db)
            bar = use_case.execute(symbol.upper())
            if bar is None:
                return f"No data available for {symbol}"
            return _format_bar(bar)
        finally:
            db.close()

    @mcp.tool(
        name="get_cached_prices",
        description=(
            "Query the local SQLite cache for OHLCV bars. "
            "Fast, no rate limits — only returns previously-fetched data. "
            "Use fetch_price_history() first to populate the cache."
        ),
    )
    def get_cached_prices(
        symbol: str,
        interval: str = "1d",
        start_date: str | None = None,
        end_date: str | None = None,
        source: str = "yfinance",
    ) -> str:
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
            if result.bar_count == 0:
                return (
                    f"No cached data for {symbol} ({source}, {interval}). "
                    f"Use fetch_price_history() to fetch and cache it first."
                )
            bars_json = [_bar_to_dict(b) for b in result.bars]
            return json.dumps(
                {
                    "symbol": result.symbol,
                    "source": result.source,
                    "interval": result.interval,
                    "bar_count": result.bar_count,
                    "bars": bars_json,
                },
                indent=2,
            )
        finally:
            db.close()

    @mcp.tool(
        name="delete_cached_prices",
        description=(
            "Delete cached OHLCV bars for a symbol. Symbol is required. "
            "Optionally narrow by source, interval, or before_date. "
            "Examples: delete all for AAPL → delete_cached_prices('AAPL'). "
            "Narrow: delete_cached_prices('AAPL', interval='1d', "
            "before_date='2024-01-01')."
        ),
    )
    def delete_cached_prices(
        symbol: str,
        source: str | None = None,
        interval: str | None = None,
        before_date: str | None = None,
    ) -> str:
        db = _get_db()
        try:
            use_case = _make_delete_cached_use_case(db)
            deleted = use_case.execute(
                symbol=symbol.upper(),
                source=source,
                interval=interval,
                before_date=before_date,
            )
            return f"Deleted {deleted} cached bars for {symbol}"
        finally:
            db.close()

    @mcp.tool(
        name="fetch_price_history",
        description=(
            "Start a BACKGROUND fetch of OHLCV data from a financial source. "
            "Returns a job_id immediately — the fetch runs async due to "
            "rate limiting. Poll progress with get_job_progress(job_id) "
            "and retrieve results with get_job_results(job_id) when complete. "
            "Fetched data is automatically saved to the local cache. "
            "Source defaults to 'yfinance'."
        ),
    )
    async def fetch_price_history(
        symbol: str,
        interval: str = "1d",
        start_date: str | None = None,
        end_date: str | None = None,
        source: str = "yfinance",
    ) -> str:
        manager = _get_job_manager()
        params = {
            "symbol": symbol.upper(),
            "source": source,
            "interval": interval,
            "start_date": start_date,
            "end_date": end_date,
        }
        job = manager.start(params, _run_fetch_job)
        return (
            f"Fetch job started for {symbol.upper()} ({source}, {interval}).\n"
            f"job_id: {job.job_id}\n"
            f"Use get_job_progress('{job.job_id}') to check status."
        )


async def _run_fetch_job(job: FetchJob) -> None:
    """Background runner: fetch prices, save to cache, update job."""
    manager = _get_job_manager()
    manager.update(job, status="running", progress_pct=10)

    try:
        db = _get_db()
        try:
            use_case = _make_fetch_prices_use_case(db)
            request = FetchPricesRequest(
                symbol=job.symbol,
                source=job.source,
                interval=job.interval,
                start_date=job.start_date,
                end_date=job.end_date,
            )
            result = use_case.execute(request)

            if result.error:
                manager.update(
                    job,
                    status="failed",
                    progress_pct=100,
                    error=result.error,
                )
                return

            bars_json = [_bar_to_dict(b) for b in result.bars]
            manager.update(
                job,
                status="completed",
                progress_pct=100,
                result=json.dumps(
                    {
                        "symbol": result.symbol,
                        "source": result.source,
                        "interval": result.interval,
                        "bar_count": result.bar_count,
                        "origin": result.origin,
                        "bars": bars_json,
                    },
                    indent=2,
                ),
            )
        finally:
            db.close()
    except asyncio.CancelledError:
        manager.update(job, status="cancelled", error="Cancelled by user")
        raise
    except Exception as exc:
        manager.update(job, status="failed", progress_pct=100, error=str(exc))


# ── Formatting helpers ────────────────────────────────────────────────────


def _format_bar(bar: PriceBar) -> str:
    """Format a single PriceBar for display."""
    return (
        f"Symbol: {bar.symbol}\n"
        f"Timestamp: {bar.timestamp}\n"
        f"Open: {bar.open}  High: {bar.high}  Low: {bar.low}  Close: {bar.close}\n"
        f"Volume: {bar.volume or 'N/A'}\n"
        f"Source: {bar.source}  Interval: {bar.interval}"
    )


def _bar_to_dict(bar: PriceBar) -> dict:
    """Convert a PriceBar to a JSON-safe dict."""
    return {
        "timestamp": bar.timestamp,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }
