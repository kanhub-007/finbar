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
        "AI agents can fetch prices, compute indicators server-side, author "
        "strategies in JSON, validate, explain, backtest, and optimize "
        "parameters — all without writing Python code.\n\n"
        # ── Quick start ──
        "QUICK START: Call get_strategy_capabilities() first, then "
        "follow the workflow below for your use case.\n\n"
        # ── Price data ──
        "PRICE DATA\n"
        "  Two sources: yfinance (stocks/ETFs) and hyperliquid (crypto).\n"
        "  Two access paths:\n"
        "    FRESH: fetch_price_history() — fetches from source, caches to "
        "SQLite, returns job_id. Rate-limited, async — poll with "
        "get_job_progress().\n"
        "    CACHED: get_cached_prices() — reads local SQLite. Instant, "
        "no rate limits, paginated. Requires prior fetch.\n\n"
        "INTERVALS: 5min, 30min, 1h, 1d, 1w\n\n"
        # ── Price tools ──
        "PRICE TOOLS\n"
        "  fetch_price_history(symbol, interval, source, start_date, "
        "end_date) → job_id\n"
        "  get_cached_prices(symbol, interval, source, start_date, "
        "end_date, page=0, page_size=500) → paginated bars + metadata\n"
        "  get_latest_quote(symbol, source='yfinance') → latest bar\n"
        "  get_symbol_info(symbol) → company/sector/exchange/market cap\n"
        "  list_cached_symbols(source) → what's cached locally\n"
        "  delete_cached_prices(symbol, source, interval, before_date)\n"
        "  list_hyperliquid_tickers(market_type) → spot/perp/hip3/all\n"
        "  get_job_progress(job_id) / get_job_results(job_id) / "
        "cancel_job(job_id)\n\n"
        # ── Indicators ──
        "INDICATORS & PROXIES\n"
        "  apply_indicators(bars_json, indicators_json) → indicator bars. "
        "Use for small datasets (<1000 bars). Supports arbitrary periods: "
        "sma_37, rsi_21, ema_100, atr_20, adx_10, bb_upper_30. Fixed: "
        "vwap, ibs, rvol, macd, ker, kama. Proxy indicators: proxy_vwap, proxy_atr, proxy_ibs, proxy_parkinson, proxy_garman_klass, proxy_expected_move, proxy_ib_high/low.\n\n"
        "  For LARGE datasets, use async indicator jobs to avoid huge "
        "payloads:\n"
        "    compute_indicators(symbol, source, interval, "
        "indicators_json) → job_id\n"
        "    get_indicator_job_progress(job_id) → status/stage/indicators\n"
        "    get_indicator_job_results(job_id, page=0, page_size=500) → "
        "paginated bars\n"
        "    cancel_indicator_job(job_id)\n\n"
        # ── Strategy SDK ──
        "STRATEGY JSON SDK\n"
        "  Define trading strategies as JSON documents. No Python code "
        "required. Supports: multi-timeframe, parameterized indicators "
        "(any period), fallback chains, formula features, ATR-based risk.\n\n"
        "  DISCOVERY\n"
        "    get_strategy_capabilities → operators, indicators, features, "
        "risk types, multi-timeframe support, period ranges\n"
        "    get_strategy_schema → JSON Schema for definitions\n"
        "    list_backtest_strategies → built-in + saved strategies\n\n"
        "  SINGLE-TIMEFRAME WORKFLOW\n"
        "    1. get_strategy_capabilities\n"
        "    2. validate_strategy_json(definition) → required indicators\n"
        "    3. explain_strategy_json(definition) → plain-language verify\n"
        "    4. fetch_price_history(symbol, interval) → job_id → poll → "
        "cached bars\n"
        "    5. compute_indicators(symbol, interval, "
        "indicators_json, timeframe_alias='primary') → job_id\n"
        "    6. (optional) compute_signals via local compute — adds "
        "confidence scores, risk flags\n"
        "    7. backtest_strategy_json(definition, bars_artifact_id="
        "job_id, symbol, interval) → metrics, trades, equity\n"
        "       Features declared in the strategy are auto-computed.\n"
        "    8. save_strategy_json(definition) → persist\n\n"
        "  MULTI-TIMEFRAME WORKFLOW\n"
        "    1. validate_strategy_json(definition) → note "
        "primary_required_indicators and informative_required_indicators "
        "(split by timeframe alias)\n"
        "    2. fetch_price_history for primary interval (e.g., 1h)\n"
        "    3. fetch_price_history for informative interval (e.g., 1d)\n"
        "    4. compute_indicators(symbol, '1h', indicators_json, "
        "timeframe_alias='primary') → primary_job_id\n"
        "    5. compute_indicators(symbol, '1d', indicators_json, "
        "timeframe_alias='daily') → daily_job_id\n"
        "    6. backtest_strategy_json(definition, bars_artifact_id="
        "primary_job_id, informative_bars_artifact_ids_json="
        "'{\"daily\":\"daily_job_id\"}', symbol, '1h')\n\n"
        "  OPTIMIZATION WORKFLOW\n"
        "    1. Complete indicator computation + backtest workflow first\n"
        "    2. start_optimization_job(definition_json, bars_artifact_id, "
        "param_ranges_json, metric, search_method, random_count)\n"
        "    3. get_optimization_job_progress(job_id) → poll\n"
        "    4. get_optimization_job_results(job_id) → ranked combinations"
        " with all metrics\n"
        "    5. cancel_optimization_job(job_id) if needed\n\n"
        "  Optimization params:\n"
        "    search_method: 'grid' (min/max/step) or 'random' (min/max/"
        "random_count)\n"
        "    metric: sharpe_ratio (default), sortino_ratio, total_return, "
        "profit_factor, win_rate, calmar_ratio\n"
        "    Max 100 combinations. Multi-timeframe supported via "
        "informative_bars_artifact_ids_json.\n\n"
        # ── Strategy features ──
        "STRATEGY FEATURES REFERENCE\n"
        "  Parameters: typed (int/float/bool/string) with defaults, "
        "min/max, {{ }} references in indicators/conditions/risk.\n"
        "  Indicators: sma, ema, rsi (required period), atr, adx, "
        "bb_upper/middle/lower (optional period). Fixed: vwap, ibs, rvol, "
        "macd/signal/hist, ker, kama.\n"
        "  Fallback: {type:'fallback', sources:['atr_1d','atr',"
        "'proxy_atr']} — tries columns in order, first available wins.\n"
        "  Features: rolling_max/min/mean/std, body_pct, range_pct, "
        "typical_price, ohlc4, shift.\n"
        "  Formula: {type:'formula', expr:{op:'and',children:[...]}} — "
        "expression trees with >,<,+,-,*,/,and,or,not,abs,neg.\n"
        "  Risk: atr stop/target, fixed_pct, risk_reward. Multipliers "
        "support {{ }} param references.\n"
        "  Timeframes: {primary:'1h', informative:[{alias:'daily',"
        "interval:'1d'}]}. Per-indicator timeframe assignment.\n\n"
        # ── All tools ──
        "ALL MCP TOOLS\n"
        "  Price: fetch_price_history, get_cached_prices, "
        "get_latest_quote, get_symbol_info, list_cached_symbols, "
        "delete_cached_prices, list_hyperliquid_tickers\n"
        "  Jobs: get_job_progress, get_job_results, cancel_job\n"
        "  TA: compute_indicators, apply_indicators\n"
        "  Metrics: compute_trading_metrics\n"
        "  Signals: compute_signals — confidence scores, RSI zones, risk flags\n"
        "  Derivatives: fetch_derivatives — CoinGlass funding rates/OI/CVD (crypto only)\n"
        "  Strategy SDK: get_strategy_capabilities, get_strategy_schema, "
        "validate_strategy_json, explain_strategy_json, "
        "backtest_strategy_json, apply_strategy_features, "
        "save_strategy_json, delete_strategy_json\n"
        "  Optimization: start_optimization_job, "
        "get_optimization_job_progress, get_optimization_job_results, "
        "cancel_optimization_job\n"
        "  Analysis: run_backtest, list_backtest_strategies, "
        "merge_and_backtest\n"
        "  Meta: get_usage_guide\n"
    )
