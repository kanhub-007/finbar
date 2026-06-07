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
        "INTERVALS: 5min, 30min, 1h, 1d, 1w\n"
        "LIMITS: yfinance intraday (5min/30min/1h) caps at ~60 days. "
        "yfinance daily/weekly and hyperliquid have multi-year history.\n\n"
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
        "vwap, ibs, rvol, macd, ker, kama. Proxy indicators: "
        "proxy_vwap, proxy_atr, proxy_ibs, proxy_parkinson, "
        "proxy_garman_klass, proxy_expected_move, proxy_ib_high/low.\n\n"
        "  For LARGE datasets, use async indicator jobs to avoid huge "
        "payloads:\n"
        "    compute_indicators(symbol, source, interval, "
        "indicators_json) → job_id\n"
        "    get_indicator_job_progress(job_id) → status/stage/indicators\n"
        "    list_artifacts(symbol, source, interval) → reusable artifact "
        "IDs + metadata, no bars\n"
        "    describe_artifact(artifact_id) → columns, date range, "
        "null counts, retention metadata\n"
        "    query_artifact_bars(artifact_id, columns_json, start_date, "
        "end_date, page, page_size) → filtered page only\n"
        "    get_indicator_job_results(job_id, page=0, page_size=500) → "
        "paginated bars for compatibility\n"
        "    delete_artifact(artifact_id) → explicit cleanup\n"
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
        "  SINGLE-TIMEFRAME ORCHESTRATION (recommended)\n"
        "    1. get_strategy_capabilities\n"
        "    2. run_strategy_pipeline(definition_json, symbol) → "
        "compact summary + result_id\n"
        "    3. get_backtest_trades / get_backtest_equity for details\n\n"
        "  SINGLE-TIMEFRAME WORKFLOW (manual)\n"
        "    1. get_strategy_capabilities\n"
        "    2. validate_strategy_definition(definition) → required indicators\n"
        "    3. explain_strategy_definition(definition) → plain-language verify\n"
        "    4. fetch_price_history(symbol, interval) → job_id → poll\n"
        "    5. compute_strategy_indicators(definition_json, symbol) → "
        "multi-timeframe job IDs\n"
        "    6. backtest_strategy_definition(definition, bars_artifact_id="
        "job_id, symbol, interval) → compact summary + result_id\n"
        "    7. save_strategy_definition(definition) → persist\n\n"
        "  MULTI-TIMEFRAME WORKFLOW\n"
        "    1. get_strategy_capabilities\n"
        "    2. validate_strategy_definition(definition) → note "
        "primary_required_indicators and informative_required_indicators\n"
        "    3. fetch_price_history for primary + informative intervals\n"
        "    4. compute_strategy_indicators(definition_json, symbol) → "
        "primary + informative job IDs\n"
        "    5. backtest_strategy_definition(definition, bars_artifact_id="
        "primary_job_id, informative_bars_artifact_ids_json="
        "'{\"daily\":\"daily_job_id\"}', symbol, '1h') "
        "→ compact summary + result_id\n"
        "    6. get_backtest_trades / get_backtest_equity for details\n\n"
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
        "informative_bars_artifact_ids_json.\n"
        "    Execution controls: risk_per_trade, leverage, commission_pct, "
        "slippage_pct, borrow_fee_annual_pct, margin_mode, "
        "maintenance_margin_pct, enable_funding, funding_rate.\n\n"
        # ── Walk-forward ──
        "  WALK-FORWARD VALIDATION\n"
        "    1. Complete indicator computation first\n"
        "    2. start_walk_forward_job(definition_json, bars_artifact_id, "
        "param_ranges_json, folds=5, train_ratio=0.7, anchor='rolling')\n"
        "    3. get_optimization_job_progress(job_id) → poll\n"
        "    4. get_optimization_job_results(job_id) → ranked results plus "
        "walk_forward_result block\n"
        "    Diagnostics: oos_sharpe, is_oos_correlation, stability, "
        "avg_rank_correlation.\n\n"
        # ── Portfolio ──
        "  PORTFOLIO BACKTESTING\n"
        "    run_portfolio_backtest(portfolio_config_json, initial_cash, "
        "interval) → portfolio equity, per-asset results, correlation.\n"
        '    Config: {"assets":[{"symbol":"AAPL","strategy_name":'
        '"sma_crossover","weight":1.0,"bars":[...]}]}\n\n'
        # ── Analytics ──
        "  BACKTEST RESULT ACCESS\n"
        "    Backtest tools store full results server-side and return "
        "compact summaries with result_id by default.\n"
        "    list_backtest_results(symbol, strategy_name) discovers stored "
        "results without trades/equity dumps.\n"
        "    get_backtest_summary(result_id, detail_level='summary') returns "
        "metrics and access pointers; detail_level='full' exports all data.\n"
        "    get_backtest_trades(result_id, page, page_size, sort_by, "
        "sort_dir) pages trades on demand.\n"
        "    get_backtest_equity(result_id, mode='daily') returns downsampled "
        "or paged equity. Modes: none, daily, weekly, drawdown_events, "
        "page, full.\n\n"
        # ── Strategy features ──
        "STRATEGY FEATURES REFERENCE\n"
        "  Parameters: typed (int/float/bool/string) with defaults, "
        "minimum/maximum bounds, {{ }} references in indicators/conditions/risk.\n"
        "  Indicators: sma, ema, rsi (required period), atr, adx, "
        "bb_upper/middle/lower (optional period). Fixed: vwap, ibs, rvol, "
        "macd/signal/hist, ker, kama.\n"
        "  Fallback: {type:'fallback', sources:['atr_1d','atr',"
        "'proxy_atr']} — tries columns in order, first available wins.\n"
        "  Features: rolling_max/min/mean/std, body_pct, range_pct, "
        "typical_price, ohlc4, shift.\n"
        "  Formula: {type:'formula', expr:{op:'and',children:[...]}} — "
        "expression trees with >,<,+,-,*,/,and,or,not,abs,neg.\n"
        "  Backtest execution controls: risk_per_trade, leverage, "
        "risk_mode, commission_pct, slippage_pct, cap_explicit_size, "
        "reject_oversized_explicit_orders, allow_negative_cash, "
        "market_calendar. Margin: margin_mode (simplified|full), "
        "borrow_fee_annual_pct, maintenance_margin_pct, enable_funding, "
        "funding_rate. Results include trust_diagnostics, analytics, "
        "reconciliation_error, and annualization_warning.\n"
        "  Risk: atr stop/target, fixed_pct, risk_reward. Multipliers "
        "support {{ }} param references.\n"
        "  Timeframes: {primary:'1h', informative:[{alias:'daily',"
        "interval:'1d'}]}. Per-indicator timeframe assignment.\n\n"
        "  SIDE RULES (entry/exit):\n"
        "    Canonical format uses entry.condition / exit.condition "
        "blocks:\n"
        "    {condition:{operator:'is_true',left:'entry_signal'}} — "
        "a condition tree where 'all'/'any'/'not' group children "
        "or a leaf has operator+left[+right].\n"
        "    Shorthand: flat condition maps are accepted inside entry/"
        "exit blocks (e.g. {entry:{operator:'<',left:'rsi_14',"
        "right:30}}) but the canonical form wraps them in .condition.\n"
        "    exit is optional; when omitted the strategy holds until "
        "stop/target or end-of-backtest.\n\n"
        # ── All tools ──
        "ALL MCP TOOLS\n"
        "  Price: fetch_price_history, get_cached_prices, "
        "get_latest_quote, get_symbol_info, list_cached_symbols, "
        "delete_cached_prices, list_hyperliquid_tickers\n"
        "  Jobs: get_job_progress, get_job_results, cancel_job\n"
        "  TA: compute_indicators, apply_indicators\n"
        "  Artifacts: list_artifacts, describe_artifact, "
        "query_artifact_bars, delete_artifact\n"
        "  Metrics: compute_trading_metrics\n"
        "  Signals: compute_signals — confidence scores, RSI zones, risk flags\n"
        "  Derivatives: fetch_derivatives — CoinGlass funding rates/OI/CVD "
        "(crypto only)\n"
        "  Strategy SDK: get_strategy_capabilities, get_strategy_schema, "
        "validate_strategy_definition, explain_strategy_definition, "
        "backtest_strategy_definition, apply_strategy_features, "
        "save_strategy_definition, delete_strategy_definition\n"
        "  Optimization: start_optimization_job, start_walk_forward_job, "
        "get_optimization_job_progress, get_optimization_job_results, "
        "cancel_optimization_job\n"
        "  Analysis: run_backtest, list_backtest_strategies, "
        "merge_and_backtest, run_portfolio_backtest\n"
        "  Pipeline: compute_strategy_indicators, run_strategy_pipeline\n"
        "  Backtest Results: list_backtest_results, get_backtest_summary, "
        "get_backtest_trades, get_backtest_equity\n"
        "  Meta: get_usage_guide\n"
    )
