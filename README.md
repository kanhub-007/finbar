# Finbar — Financial Bars & Strategy Backtesting

OHLCV price data from **yfinance** (stocks) and **Hyperliquid** (crypto — spot,
perpetuals, HIP-3) plus a **JSON strategy SDK** for AI agents. Define, validate,
explain, save, and backtest trading strategies without writing Python code.

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

## Services

| Service | URL | Default port |
|---------|-----|-------------|
| REST API | http://127.0.0.1:8000 | `FINBAR_API_PORT` |
| API Docs | http://127.0.0.1:8000/docs | — |
| MCP Server | http://127.0.0.1:8003/mcp | `FINBAR_PORT` |

---

## Strategy JSON SDK

The SDK lets AI agents author, validate, and backtest strategies through MCP
tools — no Python code required. Agents orchestrate the workflow explicitly:

```
get_strategy_capabilities → validate → explain →
fetch/query prices → apply_indicators → apply_strategy_features →
backtest → save
```

### Supported strategy features

| Feature | Example |
|---------|---------|
| Parameters | `fast_period: 20`, `slow_period: 50` |
| Indicator aliases | `fast_sma → sma_20` |
| Side-specific rules | Separate long/short entry and exit |
| Nested conditions | `all([close > sma, any([rsi < 30, volume > 1M])])` |
| Crossovers | `crosses_above`, `crosses_below` |
| Derived features | `rolling_max(high, 20).shift(1)`, `body_pct`, `typical_price` |
| Risk models | ATR stop/target, fixed %, risk/reward ratio |
| Persistence | Save validated strategies, backtest by name |

### Built-in strategies

`sma_crossover`, `rsi_mean_reversion`, `momentum_breakout`, `auction_drive` —
available as behavioral targets for JSON-authoring and for signal-level parity
testing.

### MCP tools (25+ tools)

#### Strategy SDK tools
| Tool | Description |
|------|-------------|
| `get_strategy_capabilities` | Supported operators, indicators, features, risk types |
| `get_strategy_schema` | JSON Schema for strategy definitions |
| `validate_strategy_json` | Validate + return required indicators/columns |
| `explain_strategy_json` | Human-readable explanation of a strategy |
| `backtest_strategy_json` | Backtest unsaved JSON against enriched bars or enrichment artifacts |
| `apply_strategy_features` | Calculate derived features before backtesting |
| `start_enrichment_job` | Async server-side indicator/feature enrichment from cached bars |
| `get_enrichment_job_progress` | Poll enrichment job status/stage/progress |
| `get_enrichment_job_results` | Page enriched bars from a completed job |
| `cancel_enrichment_job` | Cancel a queued/running enrichment job |
| `save_strategy_json` | Validate and persist a strategy |
| `delete_strategy_json` | Delete a saved strategy |

#### Price data tools
| Tool | Description |
|------|-------------|
| `get_usage_guide` | Full usage guide |
| `fetch_price_history` | Background fetch from source → job_id |
| `get_cached_prices` | Instant query from local SQLite cache |
| `get_job_progress` | Poll background job status |
| `get_job_results` | Retrieve completed job results |
| `cancel_job` | Cancel running fetch |
| `get_latest_quote` | Most recent OHLCV bar |
| `get_symbol_info` | Company/asset metadata |
| `list_cached_symbols` | What's in the cache |
| `delete_cached_prices` | Clear cache at ticker level |
| `list_hyperliquid_tickers` | Discover Hyperliquid tickers |

#### Analysis tools
| Tool | Description |
|------|-------------|
| `apply_indicators` | Compute indicators on supplied bars |
| `run_backtest` | Backtest a built-in or saved strategy by name |
| `list_strategies` | List all available strategies |

### Backtest output

A backtest returns everything needed for analysis and charting:

```json
{
  "total_return": 0.1235,
  "sharpe_ratio": 1.42,
  "max_drawdown": -0.0523,
  "win_rate": 0.625,
  "profit_factor": 2.31,
  "trades": [{
    "entry_date": "2024-01-15", "exit_date": "2024-01-28",
    "entry_price": 185.32, "exit_price": 192.15,
    "pnl": 321.01, "pnl_pct": 0.0369,
    "duration_bars": 9, "metadata": {"direction": "long"}
  }],
  "equity_curve": [{
    "date": "2024-01-02", "close": 185.32,
    "value": 10000.0, "drawdown": 0.0, "position": 0
  }]
}
```

Each equity curve point includes `close` — enabling equity-over-price charts
from a single response.

---

## Data Sources

| Source | Market | Interval limits |
|--------|--------|----------------|
| `yfinance` | Stocks, ETFs | 5min/30min: ~60d, 1h: ~730d, 1d/1w: full |
| `hyperliquid` | Spot, Perp, HIP-3 | 5min: ~17d, 30min: ~90d, 1h: ~208d, 1d/1w: ~3yr |

---

## Architecture

Strict clean architecture — domain → application → infrastructure → presentation.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full layer map and
design pattern catalog.

---

## Configuration

```env
FINBAR_TRANSPORT=http    # stdio or http
FINBAR_HOST=127.0.0.1
FINBAR_PORT=8003
FINBAR_API_HOST=127.0.0.1
FINBAR_API_PORT=8000
```

## Development

```bash
ruff check finbar/ && black finbar/ && pytest tests/
```

## License

MIT
