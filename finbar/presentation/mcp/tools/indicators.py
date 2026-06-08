"""MCP tools for Technical Analysis indicators and Trading Metrics."""

import json
from dataclasses import asdict

from fastmcp import FastMCP

from finbar.core.application.dto.start_indicator_job_request import (
    StartIndicatorJobRequest,
)

from ._shared import (
    _make_cancel_indicator_job_use_case,
    _make_delete_artifact_use_case,
    _make_describe_artifact_use_case,
    _make_get_indicator_job_progress_use_case,
    _make_get_indicator_job_results_use_case,
    _make_list_artifacts_use_case,
    _make_query_artifact_bars_use_case,
    _make_start_indicator_job_use_case,
)

# ── TA indicators ──
_TA_INDICATORS = [
    # Traditional TA
    "sma",
    "ema",
    "rsi",
    "macd",
    "macd_signal",
    "macd_hist",
    "atr",
    "adx",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "ker",
    "kama",
    "trend_direction",
    "trend_strength",
    "swing_high_20",
    "swing_low_20",
    # Auction Market Theory — VWAP bands
    "vwap_session",
    "vwap_upper_1",
    "vwap_lower_1",
    "vwap_upper_2",
    "vwap_lower_2",
    # Auction Market Theory — Volume Profile
    "vp_poc",
    "vp_vah",
    "vp_val",
    # Auction Market Theory — Rolling composites
    "vp_poc_5d",
    "vp_vah_5d",
    "vp_val_5d",
    "vp_poc_20d",
    "vp_vah_20d",
    "vp_val_20d",
    # Auction Market Theory — Market Profile (TPO)
    "mp_poc",
    "mp_vah",
    "mp_val",
    # Auction Market Theory — State classifiers
    "inside_value",
    "above_value",
    "below_value",
    "at_poc",
    "near_vah",
    "near_val",
    "distance_to_vah_pct",
    "distance_to_val_pct",
    "value_area_width_pct",
    "balance_status",
    # Auction Market Theory — Rule signals
    "acceptance_into_value",
    "rejection_from_edge",
    "acceptance_outside_value",
    "poc_rejection",
    "edge_volume_building",
    "value_area_migration",
]

# ── Trading Metrics ──
_TM_METRICS = [
    "vwap",
    "ibs",
    "rvol",
    "ib_high",
    "ib_low",
    "ib_range",
    "ib_midpoint",
    "price_vs_sma20",
    "breakout_signal",
    "is_power_zone",
    "breakout_quality",
    "vol_buffer_high",
    "vol_buffer_low",
    # Auction Market Theory — VWAP bands (session-scoped)
    "vwap_session",
    "vwap_upper_1",
    "vwap_lower_1",
    "vwap_upper_2",
    "vwap_lower_2",
    # Auction Market Theory — Volume Profile
    "vp_poc",
    "vp_vah",
    "vp_val",
    "vp_poc_5d",
    "vp_vah_5d",
    "vp_val_5d",
    "vp_poc_20d",
    "vp_vah_20d",
    "vp_val_20d",
    # Auction Market Theory — Market Profile (TPO)
    "mp_poc",
    "mp_vah",
    "mp_val",
    # Auction Market Theory — State + Signals
    "inside_value",
    "above_value",
    "below_value",
    "at_poc",
    "balance_status",
    "acceptance_into_value",
    "acceptance_outside_value",
    "rejection_from_edge",
    "poc_rejection",
    "edge_volume_building",
    "value_area_migration",
]

# ── Proxies (industry-standard, daily-bar substitutes) ──
_PROXIES = [
    "proxy_vwap",
    "proxy_atr",
    "proxy_ibs",
    "proxy_parkinson",
    "proxy_garman_klass",
    "proxy_rogers_satchell",
    "proxy_typical_price",
    "proxy_ohlc4",
    "proxy_iv",
    "proxy_expected_move",
    "proxy_ib_high",
    "proxy_ib_low",
]


def register_indicator_tools(mcp: FastMCP) -> None:
    """Register TA and trading-metrics computation MCP tools."""
    _register_ta_tool(mcp)
    _register_tm_tool(mcp)
    _register_progress_tool(mcp)
    _register_results_tool(mcp)
    _register_artifact_tools(mcp)
    _register_cancel_tool(mcp)


# ═══════════════════════════════════════════════════════════════════════════
# TA Indicators
# ═══════════════════════════════════════════════════════════════════════════


def _register_ta_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="compute_indicators",
        description=_ta_description(),
    )
    async def compute_indicators(
        symbol: str,
        source: str = "yfinance",
        interval: str = "1d",
        indicators_json: str = "[]",
        timeframe_alias: str = "primary",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        return _start_job(
            symbol,
            source,
            interval,
            indicators_json,
            timeframe_alias,
            start_date,
            end_date,
        )


def _ta_description() -> str:
    return (
        "Start a BACKGROUND job to compute Technical Analysis indicators "
        "(SMA, EMA, RSI, MACD, ATR, ADX, Bollinger Bands, Keltner, KAMA, "
        "swing points, trend direction/strength) and Auction Market Theory "
        "(AMT) indicators (VWAP SD bands, Volume Profile POC/VAH/VAL, "
        "Market Profile TPO POC/VAH/VAL, "
        "parameterized rolling composites vp_poc_Nd for any N, "
        "auction state classifiers, AMT rule signals) "
        "on cached OHLCV bars. "
        'Pass indicators_json like \'["sma_20","sma_50","rsi_14","atr",'
        '"vp_poc","vp_vah","vp_val","mp_poc","vp_poc_10d","balance_status"]\'. '
        "Supports arbitrary periods within catalog ranges. "
        "For multi-timeframe strategies, call once per timeframe.\n\n"
        "AMT indicators work best on intraday data (5min/30min/1h) where "
        "session-scoped profiles produce meaningful distributions. "
        "On daily bars, use rolling composites (vp_poc_Nd) for "
        "multi-day value areas.\n\n"
        "Use start_date/end_date to limit computation to a date range "
        "(e.g., start_date='2026-04-01' processes only recent bars, "
        "not the full history). This is strongly recommended for AI "
        "agents to avoid unnecessary computation. The runner "
        "auto-fetches additional prior bars needed for indicator "
        "warm-up periods (e.g., sma_200 needs 200 bars before start_date).\n\n"
        "Poll with get_indicator_job_progress(job_id), then page results "
        "with get_indicator_job_results(job_id, page, page_size)."
    )


# ═══════════════════════════════════════════════════════════════════════════
# Trading Metrics + Proxies
# ═══════════════════════════════════════════════════════════════════════════


def _register_tm_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="compute_trading_metrics",
        description=_tm_description(),
    )
    async def compute_trading_metrics(
        symbol: str,
        source: str = "yfinance",
        interval: str = "1d",
        metrics_json: str = "[]",
        timeframe_alias: str = "primary",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        return _start_job(
            symbol,
            source,
            interval,
            metrics_json,
            timeframe_alias,
            start_date,
            end_date,
        )


def _tm_description() -> str:
    return (
        "Start a BACKGROUND job to compute Trading Metrics, Proxy Metrics, "
        "and Auction Market Theory (AMT) profile indicators on cached "
        "OHLCV bars.\n\n"
        "Trading Metrics: vwap, ibs, rvol, ib_high/low/range/midpoint, "
        "price_vs_sma20, breakout_signal/level/quality, is_power_zone, "
        "vol_buffer_high/low.\n\n"
        "Proxies: proxy_vwap (typical price), proxy_ibs, proxy_atr, "
        "proxy_parkinson, proxy_garman_klass, proxy_rogers_satchell, "
        "proxy_expected_move, proxy_ib_high/low, proxy_iv.\n\n"
        "AMT Profile: vwap_session, vwap_upper_1/2, vwap_lower_1/2, "
        "vp_poc, vp_vah, vp_val (session Volume Profile), "
        "vp_poc_Nd, vp_vah_Nd, vp_val_Nd for any N (parameterized rolling), "
        "mp_poc, mp_vah, mp_val (Market Profile / TPO), "
        "inside_value, above_value, below_value, at_poc, balance_status "
        "(auction state), acceptance_into_value, acceptance_outside_value, "
        "rejection_from_edge, poc_rejection, edge_volume_building, "
        "value_area_migration (AMT rule signals).\n\n"
        "AMT indicators work best on intraday data (5min/30min/1h). "
        "On daily bars, use rolling composites for multi-day value areas.\n\n"
        'Example: metrics_json=["vwap","vp_poc","vp_vah","vp_val",'
        '"inside_value","balance_status","acceptance_outside_value"]. '
        "See get_strategy_capabilities for full catalog.\n\n"
        "Use start_date/end_date to limit computation to a date range.\n\n"
        "Poll with get_indicator_job_progress(job_id), then page results "
        "with get_indicator_job_results(job_id, page, page_size)."
    )


# ═══════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════


def _start_job(
    symbol: str,
    source: str,
    interval: str,
    items_json: str,
    timeframe_alias: str,
    start_date: str | None,
    end_date: str | None,
) -> str:
    try:
        items = json.loads(items_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"}, indent=2)
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        return json.dumps({"error": "Must be a JSON list of strings"}, indent=2)
    request = StartIndicatorJobRequest(
        symbol=symbol.upper(),
        source=source,
        interval=interval,
        mode="selected",
        indicators=items,
        definition=None,
        params={},
        timeframe_alias=timeframe_alias or "primary",
        start_date=start_date,
        end_date=end_date,
    )
    job = _make_start_indicator_job_use_case().execute(request)
    return json.dumps(
        {
            "job_id": job.job_id,
            "status": job.status,
            "symbol": job.symbol,
            "source": job.source,
            "interval": job.interval,
            "timeframe_alias": job.timeframe_alias,
        },
        indent=2,
    )


def _register_progress_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_indicator_job_progress",
        description=(
            "Check an indicator or trading-metrics job's status, progress "
            "percentage, current stage, applied indicators, and error if failed."
        ),
    )
    def get_indicator_job_progress(job_id: str) -> str:
        result = _make_get_indicator_job_progress_use_case().execute(job_id)
        return json.dumps(asdict(result), indent=2, default=str)


def _register_results_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_indicator_job_results",
        description=(
            "Return a page of bars from a completed indicator or trading-metrics "
            "job. Use page/page_size for large datasets. page is zero-based; "
            "page_size defaults to 500 and is capped at 1000."
        ),
    )
    def get_indicator_job_results(
        job_id: str,
        page: int = 0,
        page_size: int = 500,
    ) -> str:
        result = _make_get_indicator_job_results_use_case().execute(
            job_id, page, page_size
        )
        return json.dumps(asdict(result), indent=2, default=str)


def _register_artifact_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="list_artifacts",
        description=(
            "List stored indicator/trading-metric artifacts without returning "
            "bar payloads. Use this to discover reusable enriched datasets "
            "before recomputing indicators. Optional filters: symbol, source, "
            "interval. Returns artifact IDs, date ranges, columns, counts, "
            "and retention metadata."
        ),
    )
    def list_artifacts(
        symbol: str | None = None,
        source: str | None = None,
        interval: str | None = None,
    ) -> str:
        result = _make_list_artifacts_use_case().execute(symbol, source, interval)
        return json.dumps(asdict(result), indent=2, default=str)

    @mcp.tool(
        name="describe_artifact",
        description=(
            "Describe one artifact without returning bars. Returns metadata, "
            "columns, date range, indicator/feature lists, null counts, and "
            "retention metadata. Use before querying large artifacts."
        ),
    )
    def describe_artifact(artifact_id: str) -> str:
        result = _make_describe_artifact_use_case().execute(artifact_id)
        return json.dumps(asdict(result), indent=2, default=str)

    @mcp.tool(
        name="query_artifact_bars",
        description=(
            "Return a filtered page of bars from a stored artifact. Supports "
            "column selection via columns_json, date filters, and pagination. "
            "Use this instead of dumping full enriched bar payloads into chat."
        ),
    )
    def query_artifact_bars(
        artifact_id: str,
        columns_json: str = "[]",
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 0,
        page_size: int = 500,
    ) -> str:
        columns = _parse_columns(columns_json)
        if isinstance(columns, dict):
            return json.dumps(columns, indent=2)
        result = _make_query_artifact_bars_use_case().execute(
            artifact_id,
            columns or None,
            start_date,
            end_date,
            page,
            page_size,
        )
        return json.dumps(asdict(result), indent=2, default=str)

    @mcp.tool(
        name="delete_artifact",
        description=(
            "Explicitly delete a stored indicator/trading-metric artifact by "
            "artifact_id. Artifacts are durable by default and are not deleted "
            "unless this tool is called or an explicit retention policy applies."
        ),
    )
    def delete_artifact(artifact_id: str) -> str:
        result = _make_delete_artifact_use_case().execute(artifact_id)
        return json.dumps(asdict(result), indent=2, default=str)


def _parse_columns(columns_json: str) -> list[str] | dict:
    if not columns_json:
        return []
    try:
        value = json.loads(columns_json)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid columns_json: {exc}"}
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return {"error": "columns_json must be a JSON list of strings"}
    return value


def _register_cancel_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="cancel_indicator_job",
        description="Cancel a queued or running indicator or trading-metrics job.",
    )
    def cancel_indicator_job(job_id: str) -> str:
        result = _make_cancel_indicator_job_use_case().execute(job_id)
        return json.dumps(asdict(result), indent=2, default=str)
