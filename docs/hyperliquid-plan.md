# Hyperliquid Integration — Implementation Plan

> Add Hyperliquid OHLCV data to finbar following the same Strategy pattern
> as yfinance. Zero changes to domain, application, or API layers —
> just a new `StockDataFetcher` implementation + rate limiter.

---

## 1. What h-stocks Does (Reference)

h-stocks has three Hyperliquid modules:

| Module | Purpose |
|--------|---------|
| `hyperliquid_fetcher.py` | Core: rate limiter, ticker discovery (spot/perp/hip3), candle fetching |
| `hyperliquid_perp_fetcher.py` | Simplified perp-only ticker list |
| `hyperliquid_retriever_v2.py` | Chunked retrieval + `fetch_max_history()` (now → backwards until empty) |

### Three Market Types

| Type | Symbol format | API endpoint | Example |
|------|--------------|-------------|---------|
| **Spot** | Plain ticker | `spot_meta_and_asset_ctxs()` | `PURR`, `BTC` |
| **Perp** | Plain ticker | `meta_and_asset_ctxs()` | `BTC`, `ETH`, `SOL` |
| **HIP-3** | `dex:SYMBOL` (lowercase dex, uppercase coin) | `POST /info` with dex name | `flx:TSLA`, `hyperlend:BTC` |

### Rate Limiter

Token bucket (different from yfinance's sliding window):
- 1200 weight/minute, 20 weight/sec replenishment
- 80% safety margin → 960 effective max
- `candleSnapshot`: 20 + floor(candles/60) weight (~36 for 1000 candles)
- Ticker fetches: ~40 weight
- Exponential backoff with jitter on 429 errors

### Candle Fetching

- Millisecond timestamps (`start_time`, `end_time`)
- Max ~5000 bars per request → paginate with `max_bars_per_request` chunks
- HIP-3: custom `POST /info` with `dex_name` — different API path
- Returns epoch ms timestamps, converted to UTC strings
- **`fetch_max_history()` pattern**: temporal chunks from now backwards, stop when chunk is empty (IPO / genesis boundary)

### Chunk Config (from h-stocks)

| Interval | API limit | Chunk size | Bars per request |
|----------|----------|------------|-----------------|
| 5min | 17 days | 2 days | 1000 |
| 30min | 90 days | 3 days | 1000 |
| 1h | 208 days | 5 days | 1000 |
| 1d | 3 years | 60 days | 1000 |
| 1w | 3 years | 1 year | 1000 |

---

## 2. Integration Strategy — Zero Core Changes

```
                    StockDataFetcher (ABC)        ← domain — NO CHANGES
                    ├── fetch(symbol, interval, start, end)
                    ├── fetch_latest(symbol)
                    └── fetch_info(symbol)
                            │
            ┌───────────────┼───────────────┐
            │               │               │
 YFinanceStockFetcher  HyperliquidFetcher   ...  ← infrastructure — ADD THIS
```

All existing plumbing works unchanged:

- `DataSource.HYPERLIQUID` already in the enum ✅
- `fetch_price_history(symbol, interval, source="hyperliquid")` — same tool ✅
- `get_cached_prices(symbol, interval, source="hyperliquid")` — same tool ✅
- `get_latest_quote(symbol, source="hyperliquid")` — same tool ✅
- `delete_cached_prices("BTC", source="hyperliquid")` — same tool ✅
- `get_job_progress(job_id)` / `get_job_results(job_id)` — same tools ✅
- `cancel_job(job_id)` — same tool ✅
- Background job pattern (FetchJob + FetchJobManager + asyncio task) ✅
- SQLite cache (`source="hyperliquid"` column) ✅

---

## 3. What Already Works (The Background Job Pipeline)

The background job pipeline from yfinance applies identically to Hyperliquid:

```
Client                    MCP Tool                    Background Asyncio Task
  |                          |                              |
  |-- fetch_price_history ->|                              |
  |   (source="hyperliquid")|                              |
  |<-- { job_id } ----------|                              |
  |                          |-- asyncio.create_task() --->|
  |                          |                              |-- rate_limiter.wait()
  |-- get_job_progress ---->|                              |-- fetch chunk 1 (now → -60d)
  |<-- "running 30%" -------|                              |-- save to SQLite
  |                          |                              |-- fetch chunk 2 (-60d → -120d)
  |-- get_job_progress ---->|                              |-- save to SQLite
  |<-- "running 60%" -------|                              |-- ...
  |                          |                              |-- fetch chunk N → empty (genesis)
  |-- get_job_results ----->|                              |-- status="completed"
  |<-- { bars: [...] } -----|                              |
```

Key points:
- **Rate limiting**: Happens inside the background task via `HyperliquidRateLimiter.wait(weight)`. Token bucket replenishes ~20 weight/sec. The task blocks on `wait()` — no CPU burn.
- **Time range**: If no `start_date`/`end_date` provided, fetches from now backwards in temporal chunks until a chunk returns empty (genesis boundary). This is the `fetch_max_history()` pattern from h-stocks.
- **Progress tracking**: Updated after each chunk. `progress_pct` = chunks_done / estimated_total_chunks.
- **Cache**: Bars saved incrementally as each chunk completes (not all at once at the end).
- **Delete**: `delete_cached_prices("BTC", source="hyperliquid")` removes all bars for that ticker.
- **Cancel**: `cancel_job(job_id)` cancels the asyncio task mid-fetch.

---

## 4. What We Build

### `infrastructure/services/hyperliquid_rate_limiter.py`

Token bucket copied from h-stocks `HyperliquidRateLimiter`:
- `wait(weight)` — blocks until enough capacity (token bucket)
- `on_rate_limit_error()` — exponential backoff with jitter
- `on_success()` — resets error counter
- `calculate_candle_weight(num_candles)` — 20 + floor(n/60)

### `infrastructure/services/hyperliquid_fetcher.py`

Implements `StockDataFetcher`. Core flow:

```
class HyperliquidFetcher(StockDataFetcher):
    
    INTERVAL_MAP = {"5min": "5m", "30min": "30m", "1h": "1h", "1d": "1d", "1w": "1w"}
    
    # Max bars per request per interval
    MAX_BARS = {"5min": 1000, "30min": 1000, "1h": 1000, "1d": 1000, "1w": 500}
    
    # API limit per interval (in days, approximate)
    API_LIMIT_DAYS = {"5min": 17, "30min": 90, "1h": 208, "1d": 1095, "1w": 1095}
    
    def fetch(symbol, interval, start_date, end_date) -> list[PriceBar]:
        # 1. If no date range → fetch_max_history (now → backwards until empty)
        # 2. If date range → paginate through chunks
        # 3. Each chunk: rate_limiter.wait(weight) → API call → parse → validate
        # 4. Return all bars
    
    def fetch_max_history(symbol, interval) -> list[PriceBar]:
        # Temporal chunks from now backwards
        # Stop when chunk returns empty (genesis boundary)
        # Adapt from h-stocks fetch_max_history / fetch_history_efficient
    
    def _fetch_chunk(symbol, interval, start_ms, end_ms) -> list[PriceBar]:
        # Determine ticker type from symbol format:
        #   "dex:COIN" → HIP-3 (custom POST /info with dex name)
        #   plain → spot/perp (candles_snapshot)
        # Call API, parse, validate
    
    def fetch_latest(symbol) -> PriceBar | None:
        # Fetch last 24h of 1d candles, return last bar
    
    def fetch_info(symbol) -> SymbolInfo | None:
        # Return asset name from ticker metadata cache
    
    # ── Ticker discovery ──
    def fetch_spot_tickers() -> list[dict]
    def fetch_perp_tickers() -> list[dict]
    def fetch_hip3_tickers() -> list[dict]
```

### New MCP Tools

| Tool | Description |
|------|-------------|
| `list_hyperliquid_tickers(market_type)` | "spot", "perp", "hip3", or "all" |

### No API Changes Needed

All existing endpoints work with `source="hyperliquid"`:
- `POST /api/prices/fetch` — `{"symbol": "BTC", "source": "hyperliquid", "interval": "1d"}`
- `GET /api/prices/cached?symbol=BTC&source=hyperliquid&interval=1d`
- `GET /api/symbols/cached?source=hyperliquid`
- `DELETE /api/prices/cached?symbol=BTC&source=hyperliquid`
- `GET /api/jobs/{job_id}` — same for hyperliquid jobs

New endpoint:
- `GET /api/symbols/hyperliquid/tickers?type=spot` — ticker discovery

---

## 5. Implementation Sequence

| # | Task | Source |
|---|------|--------|
| 1 | Add `hyperliquid-python-sdk` to `pyproject.toml` | — |
| 2 | `hyperliquid_rate_limiter.py` — token bucket | Copy from h-stocks `HyperliquidRateLimiter` |
| 3 | `hyperliquid_fetcher.py` — implements `StockDataFetcher` | Adapt from h-stocks `HyperliquidFetcher` + chunk config |
| 4 | Wire `DataSource.HYPERLIQUID` into `_shared.py` lazy factory | Add `_get_hl_fetcher()` |
| 5 | Add `list_hyperliquid_tickers` MCP tool + API endpoint | New |
| 6 | Smoke test: fetch BTC (perp), PURR (spot), flx:TSLA (hip3) | — |

---

## 6. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Source name | `"hyperliquid"` for all three markets | Already in `DataSource` enum. Market type encoded in symbol format. |
| HIP-3 symbol format | `dex:COIN` (lowercase dex, uppercase coin) | Matches h-stocks. E.g., `flx:TSLA`, `hyperlend:BTC`. |
| Rate limiter | Separate class from yfinance | Token bucket vs sliding window — fundamentally different algorithms. |
| Ticker cache TTL | 5 minutes | Same as h-stocks. Ticker lists don't change frequently. |
| Candle limit | 5000 bars/request, paginated in 1000-bar chunks | Hyperliquid API hard limit. |
| Full history fetch | Temporal chunks from now backwards until empty | h-stocks `fetch_max_history()` pattern. |
| Background job | Reuses existing FetchPricesUseCase + FetchJobManager | Zero new code for job pipeline. |
| Delete at ticker level | `delete_cached_prices("BTC", source="hyperliquid")` | Already works. |
| Progress tracking | Updated per chunk in background task | Same as yfinance job runner. |
| `fetch_info` | Returns `SymbolInfo` with name from ticker metadata | Crypto has no "company name", "sector", etc. |
| Dependencies | `hyperliquid-python-sdk` | Official Hyperliquid Python SDK. |
