# Finbar — Financial Bars & Strategy Backtesting

OHLCV price data from **yfinance** (stocks) and **Hyperliquid** (crypto) plus a
**strategy JSON/YAML SDK** for AI agents. Define, validate, explain, backtest,
optimize, walk-forward, and persist trading strategies — no Python code required.
Strategies can be authored in **YAML** (recommended for agents — less error-prone,
no escaping hell) or JSON.

## Quick Start

```bash
git clone https://github.com/kanhub-007/finbar.git
cd finbar
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env

# REST API (port 8000)
python run_api.py          # OpenAPI docs at http://127.0.0.1:8000/docs

# MCP server (port 8003)
python run_mcp.py
```

## Documentation

| Guide | Contents |
|-------|----------|
| **[Fetching OHLCV Data](docs/DATA.md)** | Sources, intervals, fetch vs cache, job management, discovery |
| **[Technical Analysis](docs/QUANTITATIVE_PROXIES.md)** | Indicators, trading metrics, proxies, multi-timeframe |
| **[Running Backtests](docs/BACKTESTING.md)** | Execution controls, output format, analytics, trust diagnostics |
| **[Strategy JSON/YAML SDK](#strategy-capabilities-json-or-yaml)** | Authoring strategies in JSON or YAML — see `get_strategy_capabilities` and `get_usage_guide` |
| **[Optimization](docs/OPTIMIZATION.md)** | Grid search, random search, walk-forward validation, diagnostics |
| **[Architecture](docs/ARCHITECTURE.md)** | Clean architecture, layers, patterns, one class per file |
| **[Execution Model](docs/backtest_execution_model.md)** | Fill accounting, slippage, margin, annualization, crossover determinism |

## MCP Tools (44+)

| Category | Tools |
|----------|-------|
| **Data** | `fetch_price_history`, `get_cached_prices`, `get_latest_quote`, `get_symbol_info`, `list_cached_symbols`, `delete_cached_prices`, `list_hyperliquid_tickers` |
| **Jobs** | `get_job_progress`, `get_job_results`, `cancel_job` |
| **TA** | `compute_indicators`, `apply_indicators`, `compute_trading_metrics`, `get_indicator_job_progress`, `get_indicator_job_results`, `cancel_indicator_job` |
| **Artifacts** | `list_artifacts`, `describe_artifact`, `query_artifact_bars`, `delete_artifact` |
| **Signals** | `compute_signals` (confidence scores, risk flags) |
| **Derivatives** | `fetch_derivatives` (funding rates, OI, CVD — crypto) |
| **Strategy** | `get_strategy_capabilities`, `get_strategy_schema`, `validate_strategy_definition`, `explain_strategy_definition`, `backtest_strategy_definition`, `apply_strategy_features`, `save_strategy_definition`, `delete_strategy_definition` |
| **Optimization** | `start_optimization_job`, `start_walk_forward_job`, `get_optimization_job_progress`, `get_optimization_job_results`, `cancel_optimization_job` |
| **Analysis** | `run_backtest`, `list_backtest_strategies`, `run_portfolio_backtest` |
| **Pipeline** | `compute_strategy_indicators`, `run_strategy_pipeline` |
| **Results** | `list_backtest_results`, `get_backtest_summary`, `get_backtest_trades`, `get_backtest_equity` |

Call `get_usage_guide` for the full workflow reference.

## Strategy capabilities (JSON or YAML)

- **YAML-first**: Strategies can be authored in YAML — no quote escaping, native
  indentation, far less error-prone for AI agents to generate than JSON.
- **JSON also supported**: `definition_json` params accept both formats.
- **Multi-timeframe**: Primary + informative bars with column merging
- **Indicators**: sma, ema, rsi, atr, adx, bb_*, macd, ker, kama — arbitrary periods
- **Features**: rolling max/min, body_pct, formula expression trees
- **Crossovers**: `crosses_above`, `crosses_below`
- **Risk**: ATR stop/target, fixed %, risk/reward with param references
- **Side-specific**: Separate long/short entry and exit conditions
- **Optimization**: Grid search + random search with walk-forward OOS validation
- **Portfolio**: Multi-asset with weight-proportional capital and correlation

## Backtest output

Backtest tools return compact summaries by default. Full trades, equity curves,
and analytics are stored server-side and retrieved on demand.

**Default summary response:**

```json
{
  "status": "completed",
  "summary": {
    "total_return": 0.1235, "sharpe_ratio": 1.42, "max_drawdown": -0.0523,
    "win_rate": 0.625, "profit_factor": 2.31, "total_trades": 42,
    "trade_summary": {"count": 42, "avg_pnl": 150.5, "top_winners": [...], "top_losers": [...]}
  },
  "ids": {"result_id": "bt_a1b2c3d4e5f6"},
  "counts": {"trades": 42, "equity_points": 500},
  "returned": {"trades": 0, "equity_points": 0},
  "access": {
    "trades": "get_backtest_trades('bt_a1b2c3d4e5f6', page=0)",
    "equity": "get_backtest_equity('bt_a1b2c3d4e5f6', mode='daily')"
  }
}
```

Use `detail_level='full'` to get the complete result inline (legacy behavior).
Use `list_backtest_results` to discover prior results.

## Execution controls

All backtest and optimization tools accept: `leverage`, `risk_mode`,
`commission_pct`, `slippage_pct`, `risk_per_trade`, `cap_explicit_size`,
`reject_oversized_explicit_orders`, `allow_negative_cash`, `market_calendar`,
`borrow_fee_annual_pct`, `margin_mode` (`simplified`|`full`),
`maintenance_margin_pct`, `enable_funding`, `funding_rate`.

Backtest tools accept `detail_level`:

| detail_level | Behavior |
|--------------|----------|
| `summary` (default) | Metrics + trade summary + result ID, no large arrays |
| `sample` | Summary + first/last 5 trades and equity points |
| `full` | Complete inline result with all trades/equity/analytics |

## Context efficiency

Finbar is optimized for AI agents with limited context windows:

- **Agent-friendly defaults**: `get_cached_prices` defaults to the last page (most recent data).
  Use `tail=N` to get exactly N recent bars, or `metadata_only=true` for zero-bar discovery.
- **Search filtering**: `list_hyperliquid_tickers(search="MU")` and
  `list_backtest_strategies(search="crossover")` return only matching items — no 800-ticker dumps.
- **Date range guidance**: `fetch_price_history` and `compute_indicators` accept
  `start_date`/`end_date` to limit work to recent data instead of full multi-decade history.
  Tools warn agents to always pass `start_date`.
- **Efficient path documented**: `get_usage_guide` lists a 7-step preferred workflow that
  avoids the deprecated `get_cached_prices(page=0) → apply_indicators → run_backtest` pattern.
- **Artifact IDs**: Compute indicators once, reuse via `list_artifacts` + `describe_artifact`
- **Compact summaries**: Backtests return metrics + access pointers by default
- **Paginated detail**: `get_backtest_trades` and `get_backtest_equity` fetch large arrays on demand
- **Pipeline orchestration**: `run_strategy_pipeline` handles validate→compute→backtest in one call
- **Hash-based reuse**: Identical indicator requests reuse existing artifacts
- **Durable storage**: Artifacts and backtest results persist across MCP restarts

## Configuration

```env
FINBAR_TRANSPORT=http
FINBAR_HOST=127.0.0.1
FINBAR_PORT=8003
FINBAR_API_HOST=127.0.0.1
FINBAR_API_PORT=8000
```

## Development

```bash
ruff check finbar/ && black finbar/ && pytest tests/
# 376 tests in ~8s
```

## Architecture

Strict clean architecture — domain → application → infrastructure → presentation.
~185 entities, one class per file. Full dependency injection, repository pattern,
strategy pattern, facade, template method, chain of responsibility.

## License

MIT
