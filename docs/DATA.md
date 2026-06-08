# Fetching OHLCV Data

Finbar supports two data sources: **yfinance** (stocks/ETFs) and
**Hyperliquid** (crypto — spot, perpetuals, HIP-3).

## Source Selection

| Source | Markets | Interval limits |
|--------|---------|----------------|
| `yfinance` | Stocks, ETFs | 5min/30min: ~60d, 1h: ~730d, 1d/1w: full |
| `hyperliquid` | Spot, Perp, HIP-3 | 5min: ~17d, 30min: ~90d, 1h: ~208d, 1d/1w: ~3yr |

For crypto, discover available tickers with search filtering:

```
list_hyperliquid_tickers(search="MU")       # case-insensitive search
list_hyperliquid_tickers(market_type="spot")   # spot markets
list_hyperliquid_tickers(market_type="perp")   # perpetual futures
list_hyperliquid_tickers(market_type="all")    # everything
```

Always pass `search` to avoid dumping 800+ tickers into chat context.

## Fetching (fresh data)

Fetch from source — returns a `job_id` immediately. Rate-limited, runs async.
**Always pass `start_date`** to avoid fetching 40+ years of daily data:

```
fetch_price_history(
  symbol="AAPL",
  interval="1d",
  source="yfinance",
  start_date="2024-01-01",
  end_date="2024-12-31"
)
→ {"job_id": "abc-123", "status": "queued"}
```

Poll progress:

```
get_job_progress(job_id="abc-123")
→ {"status": "running", "progress_pct": 65}
```

Retrieve results when complete:

```
get_job_results(job_id="abc-123")
→ {"bars": [...], "bar_count": 252}
```

Data is automatically cached to SQLite — subsequent reads use
`get_cached_prices` without fetch.

## Querying (cached data)

Instant, no rate limits. Two preferred modes for AI agents:

### Agent mode 1: get recent bars only
```
get_cached_prices(symbol="AAPL", interval="1d", tail=100)
→ returns the last 100 bars + metadata
```
`tail=N` overrides `page` and is the recommended approach for agents.

### Agent mode 2: discover without bars
```
get_cached_prices(symbol="AAPL", interval="1d", metadata_only=true)
→ returns {symbol, source, interval, total_pages, total_bar_count,
            start_date, end_date} — no bars
```
Use this to check what's cached before deciding how much to fetch.

### Legacy mode: explicit pagination
```
get_cached_prices(
  symbol="AAPL", interval="1d",
  page=0, page_size=500
)
```

When neither `page` nor `tail` is specified, defaults to the **last page**
(most recent data), not page 0.

## Quick lookups

| Tool | Purpose |
|------|---------|
| `get_latest_quote(symbol)` | Most recent OHLCV bar |
| `get_symbol_info(symbol)` | Company name, sector, exchange, market cap |
| `list_cached_symbols(source)` | What's in the cache |
| `delete_cached_prices(symbol)` | Clear cache for a symbol |
| `list_hyperliquid_tickers(search, market_type)` | Discover crypto tickers with search |

## Job management

All background jobs (fetch, indicators, optimization) use the same pattern:

| Tool | Purpose |
|------|---------|
| `get_job_progress(job_id)` | Status, progress % |
| `get_job_results(job_id)` | Completed results |
| `cancel_job(job_id)` | Cancel running job |

## Intervals

`5min`, `30min`, `1h`, `1d`, `1w` — supported by both sources.

For multi-timeframe strategies, fetch the primary interval first (e.g., 1h),
then the informative interval (e.g., 1d). Compute indicators separately for
each timeframe before merging.
