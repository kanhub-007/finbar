# Finbar — Financial Bars & Strategy Backtesting

OHLCV price data from **yfinance** (stocks) and **Hyperliquid** (crypto) plus a
**strategy JSON SDK** for AI agents. Define, validate, explain, backtest,
optimize, walk-forward, and persist trading strategies — no Python code required.

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
| **[Strategy JSON SDK](#strategy-capabilities)** | Authoring strategies in JSON — see `get_strategy_capabilities` and `get_usage_guide` |
| **[Optimization](docs/OPTIMIZATION.md)** | Grid search, random search, walk-forward validation, diagnostics |
| **[Architecture](docs/ARCHITECTURE.md)** | Clean architecture, layers, patterns, one class per file |
| **[Execution Model](docs/backtest_execution_model.md)** | Fill accounting, slippage, margin, annualization, crossover determinism |

## MCP Tools (32+)

| Category | Tools |
|----------|-------|
| **Data** | `fetch_price_history`, `get_cached_prices`, `get_latest_quote`, `get_symbol_info`, `list_cached_symbols`, `delete_cached_prices`, `list_hyperliquid_tickers` |
| **Jobs** | `get_job_progress`, `get_job_results`, `cancel_job` |
| **TA** | `compute_indicators`, `apply_indicators`, `compute_trading_metrics` |
| **Signals** | `compute_signals` (confidence scores, risk flags) |
| **Derivatives** | `fetch_derivatives` (funding rates, OI, CVD — crypto) |
| **Strategy** | `get_strategy_capabilities`, `get_strategy_schema`, `validate_strategy_json`, `explain_strategy_json`, `backtest_strategy_json`, `apply_strategy_features`, `save_strategy_json`, `delete_strategy_json` |
| **Optimization** | `start_optimization_job`, `start_walk_forward_job`, `get_optimization_job_progress`, `get_optimization_job_results`, `cancel_optimization_job` |
| **Analysis** | `run_backtest`, `list_backtest_strategies`, `merge_and_backtest`, `run_portfolio_backtest` |

Call `get_usage_guide` for the full workflow reference.

## Strategy capabilities

- **JSON-defined**: No Python code — author strategies as structured JSON documents
- **Multi-timeframe**: Primary + informative bars with column merging
- **Indicators**: sma, ema, rsi, atr, adx, bb_*, macd, ker, kama — arbitrary periods
- **Features**: rolling max/min, body_pct, formula expression trees
- **Crossovers**: `crosses_above`, `crosses_below`
- **Risk**: ATR stop/target, fixed %, risk/reward with param references
- **Side-specific**: Separate long/short entry and exit conditions
- **Optimization**: Grid search + random search with walk-forward OOS validation
- **Portfolio**: Multi-asset with weight-proportional capital and correlation

## Backtest output

```json
{
  "total_return": 0.1235, "sharpe_ratio": 1.42, "max_drawdown": -0.0523,
  "win_rate": 0.625, "profit_factor": 2.31, "total_trades": 42,
  "trades": [{"entry_date":"...", "exit_date":"...", "pnl":321.01}],
  "equity_curve": [{"date":"...", "value":10000, "drawdown":0.0}],
  "analytics": {
    "rolling_sharpe_60": [...], "monthly_returns": {"2024-01":0.03},
    "trade_distribution": {"avg_pnl":150.5, "pnl_percentiles":{"p50":120}}
  },
  "trust_diagnostics": {
    "gap_aware_fills": true, "net_trade_metrics": true,
    "entry_model": "next_bar_open", "margin_mode": "simplified"
  }
}
```

## Execution controls

All backtest and optimization tools accept: `leverage`, `risk_mode`,
`commission_pct`, `slippage_pct`, `risk_per_trade`, `cap_explicit_size`,
`reject_oversized_explicit_orders`, `allow_negative_cash`, `market_calendar`,
`borrow_fee_annual_pct`, `margin_mode` (`simplified`|`full`),
`maintenance_margin_pct`, `enable_funding`, `funding_rate`.

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
# 361 tests in ~4.5s
```

## Architecture

Strict clean architecture — domain → application → infrastructure → presentation.
~185 entities, one class per file. Full dependency injection, repository pattern,
strategy pattern, facade, template method, chain of responsibility.

## License

MIT
