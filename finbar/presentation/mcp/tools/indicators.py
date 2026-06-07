"""MCP tools for Technical Analysis indicators and Trading Metrics."""

import json
from dataclasses import asdict

from fastmcp import FastMCP

from finbar.core.application.dto.start_indicator_job_request import (
    StartIndicatorJobRequest,
)

from ._shared import (
    _make_cancel_indicator_job_use_case,
    _make_get_indicator_job_progress_use_case,
    _make_get_indicator_job_results_use_case,
    _make_start_indicator_job_use_case,
)

# ── TA indicators ──
_TA_INDICATORS = [
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
        "swing points, trend direction/strength) on cached OHLCV bars. "
        'Pass indicators_json like \'["sma_20","sma_50","rsi_14","atr"]\'. '
        "Supports arbitrary periods within catalog ranges. "
        "For multi-timeframe strategies, call once per timeframe. "
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
        "Start a BACKGROUND job to compute Trading Metrics and industry-standard "
        "proxies on cached OHLCV bars. Trading Metrics capture market "
        "microstructure (VWAP, IBS, RVOL, Initial Balance, breakout levels, "
        "volume buffers). Proxies are mathematical substitutes for intraday "
        "metrics when backtesting on daily data — see QUANTITATIVE_PROXIES.md.\n\n"
        "Trading Metrics: vwap, ibs, rvol, ib_high/low/range/midpoint, "
        "price_vs_sma20, breakout_signal/level/quality, is_power_zone, "
        "vol_buffer_high/low.\n\n"
        "Proxies: proxy_vwap (typical price), proxy_ibs, proxy_atr, "
        "proxy_parkinson, proxy_garman_klass, proxy_rogers_satchell, "
        "proxy_expected_move, proxy_ib_high/low, proxy_iv.\n\n"
        'Example: metrics_json=\'["vwap","ibs","rvol","proxy_vwap",'
        '"proxy_ibs","proxy_parkinson"]\'. '
        "On intraday data use real metrics (vwap, ibs); on daily data use "
        "proxies (proxy_vwap, proxy_ibs). "
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


def _register_cancel_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="cancel_indicator_job",
        description="Cancel a queued or running indicator or trading-metrics job.",
    )
    def cancel_indicator_job(job_id: str) -> str:
        result = _make_cancel_indicator_job_use_case().execute(job_id)
        return json.dumps(asdict(result), indent=2, default=str)
