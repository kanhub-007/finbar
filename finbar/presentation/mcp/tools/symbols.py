"""MCP symbol tools — symbol info, list cached symbols, usage guide."""

import json

from fastmcp import FastMCP

from ._shared import (
    _get_db,
    _get_hl_tickers,
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
            "Fetches from data source if not already cached. "
            "Works for both stocks (yfinance) and crypto (hyperliquid)."
        ),
    )
    def get_symbol_info(symbol: str) -> str:
        """Look up symbol metadata."""
        db = _get_db()
        try:
            use_case = _make_get_symbol_info_use_case(db, "yfinance")
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
            try:
                symbols = use_case.execute(source=source)
            except ValueError as exc:
                return json.dumps({"error": str(exc)})
            return json.dumps(symbols, indent=2)
        finally:
            db.close()

    @mcp.tool(
        name="list_hyperliquid_tickers",
        description=(
            "List available Hyperliquid tickers by market type. "
            "Types: 'spot' (spot markets), 'perp' (perpetual futures), "
            "'hip3' (third-party DEX perpetuals), 'all' (everything). "
            "Returns ticker symbols with metadata."
        ),
    )
    def list_hyperliquid_tickers(market_type: str = "all") -> str:
        """Return Hyperliquid tickers as JSON."""
        tickers = _get_hl_tickers(market_type)
        return json.dumps(tickers, indent=2)

    @mcp.tool(
        name="get_usage_guide",
        description=(
            "Return the complete usage guide for finbar. "
            "Call this FIRST if you're new to finbar. "
            "Covers price data, indicators, strategy authoring, "
            "and backtesting workflows."
        ),
    )
    def get_usage_guide() -> str:
        return _usage_guide_text()


def _usage_guide_text() -> str:
    return (
        "FINBAR — Financial Bars & Strategy Backtesting\n"
        "=============================================\n\n"
        "Finbar provides OHLCV price data and a JSON strategy SDK. "
        "AI agents can fetch prices, apply indicators, author strategies "
        "in JSON, validate them, explain them, and run backtests.\n\n"
        # ── Price data ──
        "PRICE DATA\n"
        "  Two data sources: yfinance (stocks) and hyperliquid (crypto).\n"
        "  Two access paths:\n"
        "    FRESH: fetch_price_history() → fetches from source, caches to "
        "SQLite, returns job_id. Rate-limited, async — poll with "
        "get_job_progress().\n"
        "    CACHED: get_cached_prices() → reads local SQLite. Instant, "
        "no rate limits. Requires prior fetch.\n\n"
        "INTERVALS: 5min, 30min, 1h, 1d, 1w\n"
        "  Intraday: yfinance ~60d, hyperliquid ~17d.\n"
        "  1d/1w: full history (hyperliquid ~3 years).\n\n"
        "HYPERLIQUID TICKERS\n"
        "  spot — BTC, PURR, ETH.  perp — BTC, ETH, SOL.\n"
        "  hip3 — dex:COIN format (e.g., flx:TSLA).\n"
        "  Use list_hyperliquid_tickers('perp') to discover.\n\n"
        # ── Price tools ──
        "PRICE TOOLS\n"
        "  fetch_price_history(symbol, interval, source, start_date, end_date)"
        " → job_id\n"
        "  get_cached_prices(symbol, interval, source, start_date, end_date,"
        " page=0, page_size=500) → paginated bars\n"
        "  get_latest_quote(symbol, source='yfinance') → single OHLCV bar\n"
        "  get_symbol_info(symbol) → company name, sector, exchange, market cap\n"
        "  list_cached_symbols(source) → what's in the local cache\n"
        "  delete_cached_prices(symbol, source, interval, before_date)\n"
        "  list_hyperliquid_tickers(market_type='all') → discover HL tickers\n"
        "  get_job_progress(job_id) → poll fetch progress\n"
        "  get_job_results(job_id) → completed fetch results\n"
        "  cancel_job(job_id) → cancel running fetch\n"
        "  PAGINATION: get_cached_prices returns 500 bars per page by"
        " default (max 1000). Use page param to iterate. Response includes"
        " total_pages and total_bar_count.\n\n"
        "INDICATORS\n"
        "  apply_indicators(bars_json, indicators) → enriched bars with columns\n"
        "  indicators accepts a list (['sma_20','rsi_14']) or JSON string "
        '(\'[\\"sma_20\\",\\"rsi_14\\"]\'). '
        "Supported: sma_10/20/30/50/200, ema_12/26, rsi_7/14, macd/signal/"
        "hist, atr, adx, vwap, bb_upper/middle/lower, ibs, rvol, ker, kama, "
        "trend_direction/strength/status, swing_high_20/low_20, breakout_* "
        "and proxy_* indicators.\n\n"
        # ── Strategy SDK ──
        "STRATEGY JSON SDK\n"
        "  AI agents can define, validate, explain, and backtest trading "
        "strategies using JSON — no Python code required.\n\n"
        "  DISCOVERY\n"
        "    get_strategy_capabilities → supported operators, indicators, "
        "features, risk types\n"
        "    get_strategy_schema → JSON Schema for definitions\n"
        "    list_backtest_strategies → all available strategies (built-in + "
        "saved)\n\n"
        "  AUTHORING WORKFLOW\n"
        "    1. get_strategy_capabilities — learn what's possible\n"
        "    2. validate_strategy_json(definition) — check schema + semantics, "
        "see required indicators\n"
        "    3. explain_strategy_json(definition) — verify with plain language "
        "description\n"
        "    4. fetch_price_history or get_cached_prices — get OHLCV bars\n"
        "    5. apply_indicators(bars, ['sma_20','sma_50','atr']) — enrich "
        "bars\n"
        "    6. apply_strategy_features(definition, bars) — compute derived "
        "features like rolling_max, body_pct\n"
        "    7. backtest_strategy_json(definition, bars, symbol, interval) — "
        "run backtest\n"
        "    8. save_strategy_json(definition) — persist if happy\n\n"
        "  STRATEGY TOOLS\n"
        "    get_strategy_capabilities → operators, indicators, features, risk\n"
        "    get_strategy_schema → JSON Schema\n"
        "    validate_strategy_json(definition_json, params_json?) → errors, "
        "required indicators\n"
        "    explain_strategy_json(definition_json, params_json?) → plain text "
        "explanation\n"
        "    backtest_strategy_json(definition_json, bars_json, symbol, "
        "interval, params_json?, initial_cash) → metrics, trades, equity curve\n"
        "    apply_strategy_features(definition_json, bars_json, params_json?) "
        "→ enriched bars with derived features\n"
        "    save_strategy_json(definition_json, name_override?) → persist\n"
        "    delete_strategy_json(name) → delete saved\n\n"
        "  BUILT-IN STRATEGIES\n"
        "    sma_crossover — fast SMA crosses above/below slow SMA\n"
        "    rsi_mean_reversion — RSI oversold/overbought\n"
        "    momentum_breakout — close above prior swing high with trend filter\n"
        "    auction_drive — intraday auction market theory (requires "
        "merge_and_backtest for intraday+ daily)\n\n"
        "  SAVED STRATEGIES\n"
        "    Saved JSON strategies appear in list_backtest_strategies and can "
        "be run by name via run_backtest. They also work with "
        "backtest_strategy_json without saving (inline).\n\n"
        # ── Workflow diagrams ──
        "TYPICAL STOCK WORKFLOW\n"
        "  1. fetch_price_history('AAPL','1d','yfinance') → job_id\n"
        "  2. get_job_progress(job_id) → poll until completed\n"
        "  3. get_job_results(job_id) → bars\n"
        "  4. apply_indicators(bars, ['sma_20','sma_50']) → enriched\n"
        "  5. backtest_strategy_json(definition, enriched_bars, 'AAPL','1d')\n\n"
        "TYPICAL CRYPTO WORKFLOW\n"
        "  1. list_hyperliquid_tickers('perp') → discover\n"
        "  2. fetch_price_history('BTC','1d','hyperliquid') → job_id\n"
        "  3. get_cached_prices('BTC','1d','hyperliquid') → instant re-read\n"
        "  4. apply_indicators(bars, ['rsi_14','atr']) → enriched\n"
        "  5. backtest_strategy_json(definition, bars, 'BTC','1d')\n"
    )
