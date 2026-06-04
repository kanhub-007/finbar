# Finbar Setup Guide

## Requirements

- Python 3.12+
- Git

## Installation

```bash
git clone https://github.com/kanhub-007/finbar.git
cd finbar
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Unix
pip install -e ".[dev]"
```

## Configuration

Copy the example config and adjust:

```bash
copy .env.example .env
```

Key settings:

```env
# MCP server (HTTP mode for pi/Cursor, stdio for CLI)
FINBAR_TRANSPORT=http
FINBAR_HOST=127.0.0.1
FINBAR_PORT=8003

# REST API
FINBAR_API_HOST=127.0.0.1
FINBAR_API_PORT=8000

# Data directory (default: ./data)
# FINBAR_DATA_DIR=data

# yfinance rate limits (increase for faster fetching)
# YF_REQUESTS_PER_SECOND=2.0
# YF_REQUESTS_PER_MINUTE=60
```

## Running

### REST API

```bash
python run_api.py
```

Open http://127.0.0.1:8000/docs for interactive API docs.

### MCP Server

```bash
# HTTP mode (for pi extension)
set FINBAR_TRANSPORT=http
python run_mcp.py

# or just:
start_mcp.bat
```

The MCP server is at http://127.0.0.1:8003/mcp.

### Pi Extension

1. Start the MCP server: `start_mcp.bat`
2. Pi auto-discovers all 11 tools on session start
3. Tools are registered with `finbar_` prefix (e.g., `finbar_get_symbol_info`)

## Quick Test

```bash
# Health check
curl http://127.0.0.1:8000/api/health

# Fetch AAPL daily data
curl -X POST http://127.0.0.1:8000/api/prices/fetch \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","interval":"1d","source":"yfinance"}'

# Query cached data
curl "http://127.0.0.1:8000/api/prices/cached?symbol=AAPL&interval=1d"

# Hyperliquid: list perp tickers
curl "http://127.0.0.1:8000/api/symbols/hyperliquid/tickers?type=perp"

# Hyperliquid: fetch BTC daily
curl -X POST http://127.0.0.1:8000/api/prices/fetch \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC","interval":"1d","source":"hyperliquid"}'
```

## Development

```bash
# Lint
ruff check finbar/

# Auto-fix
ruff check finbar/ --fix

# Format
black finbar/

# Run tests
pytest tests/
```
