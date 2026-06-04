"""MCP symbol tools — symbol info, list cached symbols, usage guide."""

import json

from fastmcp import FastMCP

from ._shared import (
    _get_db,
    _make_get_symbol_info_use_case,
    _make_list_cached_use_case,
)


def register_symbol_tools(mcp: FastMCP) -> None:
    """Register all symbol-related MCP tools."""

    @mcp.tool(
        name="get_symbol_info",
        description=(
            "Get company/asset metadata for a ticker symbol. "
            "Returns company name, sector, exchange, and market cap. "
            "Fetches from yfinance if not already cached."
        ),
    )
    def get_symbol_info(symbol: str) -> str:
        """Look up symbol metadata."""
        db = _get_db()
        try:
            use_case = _make_get_symbol_info_use_case(db)
            info = use_case.execute(symbol.upper())
            if info is None:
                return f"Symbol not found: {symbol}"

            return (
                f"Symbol: {info.symbol}\n"
                f"Company: {info.company_name or 'N/A'}\n"
                f"Sector: {info.sector or 'N/A'}\n"
                f"Industry: {info.industry or 'N/A'}\n"
                f"Exchange: {info.exchange or 'N/A'}\n"
                f"Market Cap: {info.market_cap or 'N/A'}"
            )
        finally:
            db.close()

    @mcp.tool(
        name="list_cached_symbols",
        description=(
            "List all ticker symbols that have data in the local cache. "
            "Optionally filter by data source (yfinance, hyperliquid)."
        ),
    )
    def list_cached_symbols(source: str | None = None) -> str:
        """Return cached symbols as a JSON list."""
        db = _get_db()
        try:
            use_case = _make_list_cached_use_case(db)
            symbols = use_case.execute(source=source)
            return json.dumps(symbols, indent=2)
        finally:
            db.close()

    @mcp.tool(
        name="get_usage_guide",
        description=(
            "Return the complete usage guide for finbar. "
            "Call this FIRST if you're new to finbar."
        ),
    )
    def get_usage_guide() -> str:
        return _usage_guide_text()


def _usage_guide_text() -> str:
    return (
        "FINBAR — Financial Bars Microservice\n"
        "====================================\n\n"
        "Finbar provides OHLCV price data from financial data sources "
        "(yfinance, Hyperliquid) via MCP tools.\n\n"
        "DATA SOURCES\n"
        "  • yfinance — Yahoo Finance (stocks, ETFs). Rate-limited.\n"
        "  • hyperliquid — Hyperliquid DEX (crypto perpetuals). Available in v2.\n\n"
        "INTERVALS\n"
        "  5min, 30min, 1h, 1d, 1w\n"
        "  • Intraday (5min, 30min): Yahoo caps at ~60 days history.\n"
        "  • 1h: Yahoo caps at ~730 days.\n"
        "  • Daily/Weekly: Full history available.\n\n"
        "TWO DATA PATHS — CRITICAL CONCEPT\n"
        "  • FRESH: fetch_price_history() — fetches from source, saves to cache, "
        "returns job_id. Rate-limited and async — poll with get_job_progress() "
        "and retrieve with get_job_results().\n"
        "  • CACHED: get_cached_prices() — reads from local SQLite. Instant, "
        "no rate limits. Only returns previously-fetched data.\n\n"
        "TYPICAL WORKFLOW\n"
        "  1. fetch_price_history('AAPL', '1d', source='yfinance') → job_id\n"
        "  2. get_job_progress(job_id) — poll until status='completed'\n"
        "  3. get_job_results(job_id) → OHLCV bars\n"
        "  4. get_cached_prices('AAPL', '1d', source='yfinance') — instant\n\n"
        "OTHER TOOLS\n"
        "  • get_symbol_info(symbol) — company metadata\n"
        "  • get_latest_quote(symbol, source) — most recent bar\n"
        "  • list_cached_symbols(source) — what's in the cache\n"
        "  • delete_cached_prices(symbol, source, interval, before_date) "
        "— clear cache (symbol required)\n"
        "  • cancel_job(job_id) — cancel a running fetch\n"
    )
