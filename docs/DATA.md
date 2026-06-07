# Fetching OHLCV Data

Finbar supports two data sources: **yfinance** (stocks/ETFs) and
**Hyperliquid** (crypto — spot, perpetuals, HIP-3).

## Source Selection

| Source | Markets | Interval limits |
|--------|---------|----------------|
| `yfinance` | Stocks, ETFs | 5min/30min: ~60d, 1h: ~730d, 1d/1w: full |
| `hyperliquid` | Spot, Perp, HIP-3 | 5min: ~17d, 30min: ~90d, 1h: ~208d, 1d/1w: ~3yr |

For crypto, discover available tickers first:

```
list_hyperliquid_tickers(market_type="spot")   # spot markets
list_hyperliquid_tickers(market_type="perp")   # perpetual futures
list_hyperliquid_tickers(market_type="all")    # everything
```

## Fetching (fresh data)

Fetch from source — returns a `job_id` immediately. Rate-limited, runs async:

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

Instant, no rate limits, paginated:

```
get_cached_prices(
  symbol="AAPL",
  interval="1d",
  start_date="2024-01-01",
  end_date="2024-12-31",
  page=0,
  page_size=500
)
→ bars + metadata (page, total_pages, total_bar_count)
```

## Quick lookups

| Tool | Purpose |
|------|---------|
| `get_latest_quote(symbol)` | Most recent OHLCV bar |
| `get_symbol_info(symbol)` | Company name, sector, exchange, market cap |
| `list_cached_symbols(source)` | What's in the cache |
| `delete_cached_prices(symbol)` | Clear cache for a symbol |
| `list_hyperliquid_tickers(type)` | Discover crypto tickers |

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
