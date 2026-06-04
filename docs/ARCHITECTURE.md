# Finbar Architecture

Strict clean architecture per AGENTS.md — four layers plus a composition root.
Dependencies flow inward.

## Layer Map

```
finbar/
├── core/
│   ├── domain/              # Entities (frozen dataclasses), interfaces (ABCs)
│   │   ├── entities/        # PriceBar, SymbolInfo, Interval, DataSource
│   │   └── interfaces/      # StockDataFetcher, PriceCacheRepository, SymbolInfoRepository
│   └── application/         # Use cases + DTOs — depends on domain ONLY
│       ├── dto/             # FetchPricesRequest, FetchPricesResult, etc.
│       └── use_cases/       # FetchPricesUseCase, QueryCachedPricesUseCase, etc.
├── infrastructure/          # Concrete implementations
│   ├── tables/              # SQLAlchemy ORM models (PriceBar, SymbolInfo)
│   ├── data/                # DB connection (SQLite + WAL mode)
│   ├── repositories/        # SqlPriceCacheRepository, SqlSymbolInfoRepository
│   └── services/            # YFinanceStockFetcher, HyperliquidFetcher, rate limiters
├── presentation/
│   ├── api/                 # FastAPI routes + Pydantic DTOs
│   │   ├── routes/          # symbols, prices, jobs, health
│   │   └── dto/             # Request/response models
│   └── mcp/                 # FastMCP tools + job manager
│       ├── tools/           # Tool registration (symbols, prices, jobs)
│       ├── fetch_job.py     # Job state dataclass
│       └── fetch_job_manager.py  # In-memory job store
├── startup/                 # Composition root — wires everything
│   ├── bootstrap.py         # DB init + logging
│   ├── api.py               # create_app() → FastAPI
│   └── mcp.py               # create_server() → FastMCP
└── config/
    └── settings.py          # Paths, ports, rate limits
```

## Dependency Rules

| Layer | May Import From |
|-------|----------------|
| `startup/` | EVERYTHING |
| `presentation/` | application, domain, infrastructure (reads) |
| `core/application/` | domain ONLY |
| `core/domain/` | stdlib, typing, abc, dataclasses |
| `infrastructure/` | domain (implements interfaces) |

## Design Patterns

| Pattern | Where | Why |
|---------|-------|-----|
| **Strategy** | `StockDataFetcher` ABC → `YFinanceStockFetcher`, `HyperliquidFetcher` | Swappable data sources with zero core changes |
| **Repository** | `PriceCacheRepository`, `SymbolInfoRepository` ABCs → SQLite impls | Database access behind interfaces, swappable to Postgres/DuckDB |
| **Constructor DI** | All use cases receive dependencies via `__init__` | Testable, no hidden state |
| **Factory** | `startup/bootstrap.py` lazy init, `_shared.py` module-level cached | Composition root, one-time expensive init |
| **DTO** | `core/application/dto/` + `presentation/api/dto/` | Data crossing boundaries uses dedicated objects |
| **Background Job** | `FetchJob` + `FetchJobManager` + `asyncio.to_thread()` | Rate-limited fetches don't block the event loop |

## Data Flow

### Fresh fetch (async, rate-limited)

```
Client → fetch_price_history(symbol, interval, source) → job_id
  → Background thread:
      1. Rate limiter.wait()
      2. Source API call (yfinance / Hyperliquid)
      3. Parse + validate bars
      4. Save to SQLite (INSERT OR REPLACE UPSERT)
      5. Update job status → completed
  → Client polls get_job_progress(job_id) → get_job_results(job_id)
```

### Cached query (sync, instant)

```
Client → get_cached_prices(symbol, interval, source) → SQLite SELECT → bars
```

### Delete at ticker level

```
Client → delete_cached_prices(symbol, source, interval, before_date) → DELETE FROM price_bar
Symbol is required — prevents accidental full-wipe.
```

## Two Data Sources

| | yfinance | Hyperliquid |
|---|---------|-------------|
| Rate limiter | Sliding window (30 req/min) | Token bucket (1200 weight/min) |
| Symbols | Stock tickers (AAPL, TSLA) | Plain (BTC, PURR) or dex:COIN (flx:TSLA) |
| Full history | `period="max"` (unlimited for daily) | Chunked backwards until empty (~3 years daily) |
| SDK | `yfinance` | `hyperliquid-python-sdk` |

## Database Schema (SQLite)

```sql
CREATE TABLE price_bar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    source TEXT NOT NULL,
    interval TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    open REAL NOT NULL, high REAL NOT NULL,
    low REAL NOT NULL, close REAL NOT NULL,
    volume INTEGER,
    UNIQUE(symbol, source, interval, timestamp)
);

CREATE TABLE symbol_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT UNIQUE NOT NULL,
    company_name TEXT, sector TEXT, industry TEXT,
    exchange TEXT, market_cap REAL, fetched_at TEXT
);
```
