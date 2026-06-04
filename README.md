# Finbar — Financial Bars Microservice

Raw OHLCV price data from **yfinance** (stocks) and **Hyperliquid** (crypto —
spot, perpetuals, HIP-3) via MCP tools and REST API. Cache-enabled with
background fetch jobs.

## Quick Start

```bash
# Clone and set up
git clone https://github.com/kanhub-007/finbar.git
cd finbar
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# Copy and customize config
copy .env.example .env

# Start the REST API (port 8000)
python run_api.py
# → OpenAPI docs at http://127.0.0.1:8000/docs

# Start the MCP server (port 8003)
python run_mcp.py
# Set FINBAR_TRANSPORT=http in .env for HTTP transport
```

## Services

| Service | URL | Default port |
|---------|-----|-------------|
| REST API | http://127.0.0.1:8000 | `FINBAR_API_PORT` |
| API Docs | http://127.0.0.1:8000/docs | — |
| MCP Server | http://127.0.0.1:8003/mcp | `FINBAR_PORT` |

## MCP Tools (11 tools)

| Tool | Description |
|------|-------------|
| `get_usage_guide` | Full usage guide — call this first |
| `fetch_price_history` | Background fetch from source → job_id |
| `get_cached_prices` | Instant query from local SQLite cache |
| `get_job_progress` | Poll background job status |
| `get_job_results` | Retrieve completed job results |
| `cancel_job` | Cancel running fetch |
| `get_latest_quote` | Most recent OHLCV bar |
| `get_symbol_info` | Company/asset metadata |
| `list_cached_symbols` | What's in the cache |
| `delete_cached_prices` | Clear cache at ticker level |
| `list_hyperliquid_tickers` | Discover Hyperliquid spot/perp/hip3 tickers |

## Data Sources

| Source | Market | Interval limits |
|--------|--------|----------------|
| `yfinance` | Stocks, ETFs | 5min/30min: ~60d, 1h: ~730d, 1d/1w: full |
| `hyperliquid` | Spot, Perp, HIP-3 | 5min: ~17d, 30min: ~90d, 1h: ~208d, 1d/1w: ~3yr |

## Architecture

Strict clean architecture — domain → application → infrastructure → presentation.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Configuration

Copy `.env.example` to `.env` and adjust:

```env
FINBAR_TRANSPORT=http    # stdio or http
FINBAR_HOST=127.0.0.1
FINBAR_PORT=8003
FINBAR_API_HOST=127.0.0.1
FINBAR_API_PORT=8000
```

## Development

```bash
# Lint and format
ruff check finbar/
black finbar/

# Run tests
pytest tests/
```

## Pi Extension

The `.pi/extensions/finbar.ts` extension auto-discovers MCP tools when the
server is running. The server must be started first:

```bash
start_mcp.bat
```

## License

MIT
