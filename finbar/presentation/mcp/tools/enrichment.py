"""MCP enrichment tools — asynchronous server-side indicator/feature jobs."""

import json
from dataclasses import asdict

from fastmcp import FastMCP

from finbar.core.application.dto.start_enrichment_job_request import (
    StartEnrichmentJobRequest,
)
from finbar.core.domain.entities.enrichment_job import EnrichmentJob

from ._shared import (
    _make_cancel_enrichment_job_use_case,
    _make_get_enrichment_job_progress_use_case,
    _make_get_enrichment_job_results_use_case,
    _make_start_enrichment_job_use_case,
)

_SUPPORTED_MODES = {"selected", "strategy_required"}


def register_enrichment_tools(mcp: FastMCP) -> None:
    """Register async enrichment MCP tools."""
    _register_start_enrichment_tool(mcp)
    _register_progress_tool(mcp)
    _register_results_tool(mcp)
    _register_cancel_tool(mcp)


def _register_start_enrichment_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="start_enrichment_job",
        description=_start_description(),
    )
    async def start_enrichment_job(
        symbol: str,
        source: str = "yfinance",
        interval: str = "1d",
        mode: str = "selected",
        indicators_json: str = "[]",
        definition_json: str = "",
        params_json: str = "{}",
        timeframe_alias: str = "primary",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        """Start an async enrichment job and return its job id."""
        parsed = _parse_start_inputs(indicators_json, params_json, mode)
        if "error" in parsed:
            return json.dumps(parsed)
        request = _start_request(
            symbol,
            source,
            interval,
            mode,
            parsed,
            definition_json,
            timeframe_alias,
            start_date,
            end_date,
        )
        job = _make_start_enrichment_job_use_case().execute(request)
        return json.dumps(_start_payload(job), indent=2)


def _register_progress_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_enrichment_job_progress",
        description=(
            "Check an enrichment job's status, progress percentage, current "
            "stage, applied indicators/features, and error if failed."
        ),
    )
    def get_enrichment_job_progress(job_id: str) -> str:
        """Return progress for an enrichment job."""
        result = _make_get_enrichment_job_progress_use_case().execute(job_id)
        return json.dumps(asdict(result), indent=2, default=str)


def _register_results_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_enrichment_job_results",
        description=(
            "Return a page of enriched bars from a completed enrichment job. "
            "Use page/page_size for large datasets. page is zero-based; "
            "page_size defaults to 500 and is capped at 1000."
        ),
    )
    def get_enrichment_job_results(
        job_id: str,
        page: int = 0,
        page_size: int = 500,
    ) -> str:
        """Return paginated enrichment job results."""
        result = _make_get_enrichment_job_results_use_case().execute(
            job_id, page, page_size
        )
        return json.dumps(asdict(result), indent=2, default=str)


def _register_cancel_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="cancel_enrichment_job",
        description="Cancel a queued or running enrichment job.",
    )
    def cancel_enrichment_job(job_id: str) -> str:
        """Cancel an enrichment job."""
        result = _make_cancel_enrichment_job_use_case().execute(job_id)
        return json.dumps(asdict(result), indent=2, default=str)


def _start_description() -> str:
    return (
        "Start a BACKGROUND enrichment job using cached OHLCV bars, without "
        "passing a huge bars_json payload. Use mode='selected' with "
        'indicators_json like \'["sma_20","rsi_14"]\', or '
        "mode='strategy_required' with definition_json to calculate the "
        "indicators required by a strategy JSON. For multi-timeframe "
        "strategies, call once per timeframe and set timeframe_alias "
        "('primary', 'daily', etc.). Poll with "
        "get_enrichment_job_progress(job_id), then page results with "
        "get_enrichment_job_results(job_id, page, page_size)."
    )


def _start_request(
    symbol: str,
    source: str,
    interval: str,
    mode: str,
    parsed: dict,
    definition_json: str,
    timeframe_alias: str,
    start_date: str | None,
    end_date: str | None,
) -> StartEnrichmentJobRequest:
    return StartEnrichmentJobRequest(
        symbol=symbol.upper(),
        source=source,
        interval=interval,
        mode=mode,
        indicators=parsed["indicators"],
        definition=definition_json or None,
        params=parsed["params"],
        timeframe_alias=timeframe_alias or "primary",
        start_date=start_date,
        end_date=end_date,
    )


def _start_payload(job: EnrichmentJob) -> dict:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "symbol": job.symbol,
        "source": job.source,
        "interval": job.interval,
        "mode": job.mode,
        "timeframe_alias": job.timeframe_alias,
    }


def _parse_start_inputs(indicators_json: str, params_json: str, mode: str) -> dict:
    if mode not in _SUPPORTED_MODES:
        return {"error": f"mode must be one of {sorted(_SUPPORTED_MODES)}"}
    try:
        indicators = json.loads(indicators_json)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid indicators_json: {exc}"}
    if not isinstance(indicators, list) or not all(
        isinstance(item, str) for item in indicators
    ):
        return {"error": "indicators_json must be a JSON list of strings"}
    try:
        params = json.loads(params_json)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid params_json: {exc}"}
    if not isinstance(params, dict):
        return {"error": "params_json must be a JSON object"}
    return {"indicators": indicators, "params": params}
