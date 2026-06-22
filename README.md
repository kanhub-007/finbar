# Finbar — Financial Bars & Strategy Backtesting

OHLCV price data from **yfinance** (stocks) and **Hyperliquid** (crypto) plus a
**strategy JSON/YAML SDK** for AI agents. Define, validate, explain, backtest,
optimize, walk-forward, and persist trading strategies — no Python code required.
Strategies can be authored in **YAML** (recommended for agents — less error-prone,
no escaping hell) or JSON.

## What's New (Jun 2026)

### Causal Streaming Enrichment (`live_parity_streaming`)

All backtests now default to **causal enrichment** — each bar's indicators are
computed using only data available at that bar's close, with no future lookahead.
This is the **live-tradable** mode: what Finbot would actually see in real trading.

**Two enrichment modes:**
- **`live_parity_streaming`** (DEFAULT, RECOMMENDED): Causal streaming via
  `CausalMultiTimeframeStreamingEnricher`. Required for VP/AMT session-based
  strategies. Safe for all strategy types.
- **`batch_full_frame`** (RESEARCH ONLY): Legacy full-frame batch enrichment.
  NOT live-parity safe for session VP/AMT indicators (lookahead bias). Kept for
  TA-only strategies and historical comparison.

Backtest results now include `enrichment_mode`, `live_parity_safe`, and
`parity_warnings` metadata so you can verify the mode was applied correctly.

### Async Strategy Pipeline

Large causal backtests can take minutes. The new async pipeline tools eliminate
the MCP timeout:

```
start_strategy_pipeline(definition, symbol, ...)     → job_id (instant)
get_strategy_pipeline_progress(job_id)               → poll until "completed"
get_strategy_pipeline_results(job_id)                → full backtest result
```

### Performance Optimizations

The causal streaming engine was optimized with three techniques:
- **Incremental session VP**: `IncrementalSessionVpState` computes VP per-session
  (O(session_size)) instead of full-window recompute (O(500))
- **Batched windowed metrics**: `BatchedWindowedState` computes all windowed
  metrics in one batch call per bar (10× reduction for AMT strategies)
- **Parallel timeframe enrichment**: Informative engines run in parallel threads
- **VP injection**: Incremental VP values feed the batched state to avoid
  duplicate dependency recompute

Result: **~80× faster** for the AMT MTF strategy (200→14ms/bar).

### Finbot-Ready Causal Enricher API

The package exposes a Finbot-facing API for live candle processing:

```python
enricher = CausalMultiTimeframeStreamingEnricher.from_strategy_definition(
    definition, primary_indicators, informative_indicators
)
for event in closed_candle_events:
    latest = enricher.update(event.timeframe_alias, event.bar)
    if latest.is_ready:
        signal = JsonRuleBasedStrategy(definition).on_bar(latest.values, position=None)
```

### MCP Tool Improvements

- Fixed `asyncio.create_task` crash when MCP runs sync tools on thread pool
- `compute_strategy_indicators` now properly async (was blocking the event loop)
- All enrichment mode parameters documented in tool descriptions
- Granular progress reporting during async pipeline execution

## Quick Start

```bash
git clone https://github.com/kanhub-007/finbar.git
cd finbar
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env

# REST API (port 8000)
python run_api.py          # OpenAPI docs at http://127.0.0.1:8000/docs

# MCP server (port 8003)
python run_mcp.py
```

## Documentation

| Guide | Contents |
|-------|----------|
| **[Fetching OHLCV Data](docs/DATA.md)** | Sources, intervals, fetch vs cache, job management, discovery |
| **[Technical Analysis](docs/QUANTITATIVE_PROXIES.md)** | Indicators, trading metrics, proxies, AMT profiles, multi-timeframe |
| **[Running Backtests](docs/BACKTESTING.md)** | Execution controls, output format, analytics, trust diagnostics |
| **[Strategy JSON/YAML SDK](#strategy-capabilities-json-or-yaml)** | Authoring strategies in JSON or YAML — see `get_strategy_capabilities` and `get_usage_guide` |
| **[Optimization](docs/OPTIMIZATION.md)** | Grid search, random search, walk-forward validation, diagnostics |
| **[Architecture](docs/ARCHITECTURE.md)** | Clean architecture, layers, patterns, one class per file |
| **[Execution Model](docs/BACKTEST_EXECUTION_MODEL.md)** | Fill accounting, slippage, margin, annualization, crossover determinism |

## MCP Tools (50+)

| Category | Tools |
|----------|-------|
| **Data** | `fetch_price_history`, `get_cached_prices`, `get_latest_quote`, `get_symbol_info`, `list_cached_symbols`, `delete_cached_prices`, `list_hyperliquid_tickers` |
| **Jobs** | `get_job_progress`, `get_job_results`, `cancel_job` |
| **TA** | `compute_indicators`, `apply_indicators`, `compute_trading_metrics`, `get_indicator_job_progress`, `get_indicator_job_results`, `cancel_indicator_job` |
| **Artifacts** | `list_artifacts`, `describe_artifact`, `query_artifact_bars`, `delete_artifact` |
| **Signals** | `compute_signals` (confidence scores, risk flags) |
| **Derivatives** | `fetch_derivatives` (funding rates, OI, CVD — crypto) |
| **Metrics** | `list_market_metrics`, `check_metric`, `resolve_metric` |
| **Strategy** | `get_strategy_capabilities`, `get_strategy_schema`, `validate_strategy_definition`, `explain_strategy_definition`, `backtest_strategy_definition`, `apply_strategy_features`, `save_strategy_definition`, `delete_strategy_definition` |
| **Optimization** | `start_optimization_job`, `start_walk_forward_job`, `get_optimization_job_progress`, `get_optimization_job_results`, `cancel_optimization_job` |
| **Analysis** | `run_backtest`, `list_backtest_strategies`, `run_portfolio_backtest` |
| **Pipeline** | `compute_strategy_indicators`, `run_strategy_pipeline`, `start_strategy_pipeline`, `get_strategy_pipeline_progress`, `get_strategy_pipeline_results`, `cancel_strategy_pipeline` |
| **Results** | `list_backtest_results`, `get_backtest_summary`, `get_backtest_trades`, `get_backtest_equity` |
| **Guides** | `get_usage_guide` (full workflow reference) |

## Enrichment Modes

| Mode | Default | Safe For | Use Case |
|------|---------|----------|----------|
| **`live_parity_streaming`** | ✅ Yes | All strategies | Live-tradable results; what Finbot would see |
| `batch_full_frame` | No | TA-only (sma, rsi, macd) | Research, historical comparison |

**When in doubt, omit the `enrichment_mode` parameter** — the default is always correct.

The usage guide (`get_usage_guide`) documents both modes at the top. Tool
descriptions for `backtest_strategy_definition`, `run_strategy_pipeline`, and
`run_backtest` all explain when to use each.

## Strategy capabilities (JSON or YAML)

- **YAML-first**: Strategies can be authored in YAML — no quote escaping, native
  indentation, far less error-prone for AI agents to generate than JSON.
- **JSON also supported**: `definition_json` params accept both formats.
- **Multi-timeframe**: Primary + informative bars with column merging
- **Indicators**: sma, ema, rsi, atr, adx, bb_*, macd, ker, kama — arbitrary periods
- **AMT (Auction Market Theory)**: VWAP SD bands, Volume Profile (POC/VAH/VAL),
  Market Profile (TPO), rolling composites, auction state classifiers, AMT rule signals
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
    "enrichment_mode": "live_parity_streaming",
    "live_parity_safe": true,
    "parity_warnings": [],
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
- **Async pipeline**: `start_strategy_pipeline` for long-running causal backtests — no timeout
- **Hash-based reuse**: Identical indicator requests reuse existing artifacts
- **Durable storage**: Artifacts and backtest results persist across MCP restarts

## Strategy Runtime Package (`finbar_strategy_runtime`)

The shared package owns all enrichment semantics. Both Finbar (backtests) and
Finbot (live trading) consume the same `CausalMultiTimeframeStreamingEnricher`:

```python
from finbar_strategy_runtime.indicators.causal_multi_timeframe_streaming_enricher import (
    CausalMultiTimeframeStreamingEnricher,
)

# One-call enrichment (backtest/replay)
frame = CausalMultiTimeframeStreamingEnricher.causal_enrich_bars(
    primary_bars, informative_bars, definition,
    primary_indicators, informative_indicators,
)

# Live candle processing (Finbot)
enricher = CausalMultiTimeframeStreamingEnricher.from_strategy_definition(
    definition, primary_indicators, informative_indicators,
)
enricher.update("h1", h1_bar)         # informative → returns None
latest = enricher.update("primary", primary_bar)  # → CausalEnrichedBar
signal = strategy.on_bar(latest.values, position=None)
```

### Performance architecture

| Component | Technique | Impact |
|-----------|-----------|--------|
| `IncrementalSessionVpState` | Session-scoped VP recompute (O(48) vs O(500)) | ~5× |
| `BatchedWindowedState` | One batch compute for all windowed metrics | ~10× |
| VP injection | Incremental VP feeds batched state (no duplicate recompute) | Eliminates O(n²) |
| Parallel enrichment | Informative engines in parallel threads | ~1.5× |
| `causal_enrich_bars` | Timestamps parsed in batch, not per-bar | Eliminates per-bar overhead |

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
# ~590 tests in finbar/ (~6min); ~970 in packages/strategy-runtime (~6min)
```

## Architecture

Strict clean architecture — domain → application → infrastructure → presentation.
~185 entities, one class per file. Full dependency injection, repository pattern,
strategy pattern, facade, template method, chain of responsibility.

## License

MIT
