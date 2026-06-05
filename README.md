# Finbar — Financial Bars & Strategy Backtesting

OHLCV price data from **yfinance** (stocks) and **Hyperliquid** (crypto — spot,
perpetuals, HIP-3) plus a **strategy JSON SDK** for AI agents. Define, validate,
explain, backtest, optimize, and persist trading strategies without writing
Python code.

## Quick Start

```bash
git clone https://github.com/kanhub-007/finbar.git
cd finbar
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env

# Start the REST API (port 8000)
python run_api.py
# → OpenAPI docs at http://127.0.0.1:8000/docs

# Start the MCP server (port 8003)
python run_mcp.py
```

## Strategy JSON SDK

The SDK lets AI agents author, validate, and backtest strategies through MCP
tools — no Python code required. Full workflow:

```
get_strategy_capabilities → validate → explain →
fetch/query prices → compute_indicators / compute_trading_metrics →
backtest_strategy_json (artifact-backed) → start_optimization_job →
save_strategy_json
```

### Supported strategy features

| Category | Features |
|----------|----------|
| **Multi-timeframe** | Primary (e.g., 1h) + informative (e.g., 1d) with column merging |
| **Parameters** | Typed parameters with defaults, min/max validation, `{{ }}` references |
| **Indicators** | sma, ema, rsi, atr, adx, bb_upper/middle/lower, macd, ker, kama — all with arbitrary periods |
| **Trading Metrics** | vwap, ibs, rvol, ib_*, price_vs_sma20, breakout_*, vol_buffer_* — market microstructure |
| **Proxies** | Industry-standard mathematical substitutes for daily bars — see [Proxies](docs/QUANTITATIVE_PROXIES.md) |
| **Multi-timeframe** | Primary (e.g., 1h) + informative (e.g., 1d), daily columns merged with `_1d` suffix |
| **Side-specific rules** | Separate long/short entry and exit conditions |
| **Nested conditions** | `all([close > sma, any([rsi < 30, rvol > 1.5])])` |
| **Crossovers** | `crosses_above`, `crosses_below` |
| **Derived features** | `rolling_max`, `rolling_min`, `body_pct`, `typical_price`, `ohlc4` |
| **Formula features** | Expression trees: comparisons, arithmetic, logical `and`/`or`/`not` |
| **Risk models** | ATR stop/target, fixed %, risk/reward ratio — all with `{{ }}` param refs |
| **Parameter optimization** | Grid search (min/max/step) + random search — ranked by any metric |
| **Persistence** | Artifacts survive restarts (SQLite), strategies saved by name |

### Built-in strategies

`sma_crossover`, `rsi_mean_reversion`, `momentum_breakout`, `auction_drive` —
also available as a JSON fixture (`tests/fixtures/strategies/auction_drive_json.json`)
using multi-timeframe with daily trend context and industry-standard trading proxies.

### MCP tools (28+ tools)

#### Strategy SDK tools
| Tool | Description |
|------|-------------|
| `get_strategy_capabilities` | Supported operators, indicators, features, risk types, multi-timeframe |
| `get_strategy_schema` | JSON Schema for strategy definitions |
| `validate_strategy_json` | Validate + return required indicators split by timeframe |
| `explain_strategy_json` | Human-readable explanation of a strategy |
| `backtest_strategy_json` | Backtest via indicator bars or artifact ID |
| `apply_strategy_features` | Calculate derived features (formula, rolling, body_pct) before backtesting |
| `save_strategy_json` | Validate and persist a strategy |
| `delete_strategy_json` | Delete a saved strategy |

#### Technical Analysis & Trading Metrics
| Tool | Description |
|------|-------------|
| `compute_indicators` | TA: sma, ema, rsi, macd, atr, adx, bb_*, ker, kama, swing_*, trend_* |
| `compute_trading_metrics` | TM + proxies: vwap, ibs, rvol, ib_*, breakout_*, proxy_vwap, proxy_ibs, proxy_parkinson, … |
| `apply_indicators` | Sync TA + TM on supplied bars (small datasets) |
| `get_indicator_job_progress` | Poll computation status, stage, indicators applied |
| `get_indicator_job_results` | Page computed bars (page/page_size) from completed job |
| `cancel_indicator_job` | Cancel a running computation |

#### Optimization tools
| Tool | Description |
|------|-------------|
| `start_optimization_job` | Grid/random search over parameter ranges, ranked by metric |
| `get_optimization_job_progress` | Poll optimization progress (combinations done/total) |
| `get_optimization_job_results` | Ranked results with all backtest metrics per combination |
| `cancel_optimization_job` | Cancel a running optimization job |

#### Price data tools
| Tool | Description |
|------|-------------|
| `get_usage_guide` | Full usage guide with workflows |
| `fetch_price_history` | Background fetch from source → job_id (rate-limited) |
| `get_cached_prices` | Instant paginated query from SQLite (page/page_size) |
| `get_job_progress` | Poll fetch job status |
| `get_job_results` | Retrieve completed fetch results |
| `cancel_job` | Cancel running fetch |
| `get_latest_quote` | Most recent OHLCV bar |
| `get_symbol_info` | Company/asset metadata |
| `list_cached_symbols` | What's in the cache |
| `delete_cached_prices` | Clear cache at ticker level |
| `list_hyperliquid_tickers` | Discover Hyperliquid tickers (spot, perp, HIP-3) |

#### Analysis tools
| Tool | Description |
|------|-------------|
| `run_backtest` | Backtest a built-in or saved strategy by name |
| `list_backtest_strategies` | List all available strategies |
| `merge_and_backtest` | Multi-timeframe backtest for built-in strategies |

### Backtest output

```json
{
  "total_return": 0.1235, "sharpe_ratio": 1.42, "max_drawdown": -0.0523,
  "win_rate": 0.625, "profit_factor": 2.31,
  "trades": [{
    "entry_date": "2024-01-15", "exit_date": "2024-01-28",
    "entry_price": 185.32, "exit_price": 192.15,
    "pnl": 321.01, "pnl_pct": 0.0369, "duration_bars": 9
  }],
  "equity_curve": [{
    "date": "2024-01-02", "close": 185.32,
    "value": 10000.0, "drawdown": 0.0, "position": 0
  }]
}
```

---

## Data Sources

| Source | Market | Interval limits |
|--------|--------|----------------|
| `yfinance` | Stocks, ETFs | 5min/30min: ~60d, 1h: ~730d, 1d/1w: full |
| `hyperliquid` | Spot, Perp, HIP-3 | 5min: ~17d, 30min: ~90d, 1h: ~208d, 1d/1w: ~3yr |

---

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
```

## Architecture

Strict clean architecture — domain → application → infrastructure → presentation.
171 classes, one per file.

## License

MIT
