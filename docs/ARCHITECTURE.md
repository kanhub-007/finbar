# Finbar Architecture

Strict clean architecture per AGENTS.md — four layers plus a composition root.
Dependencies flow inward. One class per file enforced mechanically (171 classes,
zero multi-class files in `finbar/`).

## Layer Map

```
finbar/
├── core/
│   ├── domain/
│   │   ├── entities/        # Frozen dataclasses — no frameworks
│   │   │   ├── strategy_definition.py   # Parsed strategy (parameters, indicators,
│   │   │   │                             #   features, risk, sides, timeframes)
│   │   │   ├── strategy_document.py     # Persisted JSON strategy with metadata
│   │   │   ├── condition.py             # Atomic condition (left op right)
│   │   │   ├── condition_group.py       # Nested all/any/not group
│   │   │   ├── operand.py              # Typed value with optional fallback sources
│   │   │   ├── indicator_spec.py       # Alias → concrete column + timeframe + fallbacks
│   │   │   ├── feature_spec.py         # Derived feature (rolling, formula, body_pct)
│   │   │   ├── formula_node.py         # Expression AST node for formula features
│   │   │   ├── risk_spec.py            # Stop-loss / take-profit settings
│   │   │   ├── side_rules.py           # Entry + exit conditions per side
│   │   │   ├── strategy_parameter.py   # Typed runtime parameter
│   │   │   ├── strategy_meta.py        # Strategy metadata for discovery
│   │   │   ├── strategy_kind.py        # BUILTIN / USER_DEFINED enum
│   │   │   ├── strategy_validation_error.py  # Path-specific diagnostic
│   │   │   ├── strategy_validation_result.py # Parse/validate output + timeframe info
│   │   │   ├── timeframe_declaration.py # Primary + informative timeframe config
│   │   │   ├── informative_timeframe.py # Named informative timeframe (alias, interval)
│   │   │   ├── signal_result.py        # Bar-by-bar trading signal
│   │   │   ├── price_bar.py            # OHLCV + timestamp
│   │   │   ├── data_source.py          # yfinance / hyperliquid enum
│   │   │   ├── data_mode.py            # REAL / PROXY enum
│   │   │   ├── interval.py             # Bar interval value object
│   │   │   ├── symbol_info.py          # Company/asset metadata
│   │   │   ├── indicator_job.py       # Enrichment job state (async)
│   │   │   ├── optimization_job.py     # Optimization job state (async)
│   │   │   ├── optimization_result.py  # Single combination backtest metrics
│   │   │   └── param_range.py          # Min/max/step range for grid/random search
│   │   ├── interfaces/     # ABCs — contracts for outer layers
│   │   │   ├── trading_strategy.py              # on_bar(), on_reset(), meta()
│   │   │   ├── strategy_provider.py              # create(), list_metadata()
│   │   │   ├── strategy_definition_strategy_factory.py  # compile definition → strategy
│   │   │   ├── strategy_document_repository.py   # CRUD for saved strategies
│   │   │   ├── strategy_definition_parser.py      # Parse JSON → domain entities
│   │   │   ├── strategy_feature_calculator.py      # Calculate derived features
│   │   │   ├── formula_feature_calculator.py       # Evaluate formula expression ASTs
│   │   │   ├── risk_price_calculator.py            # Stop/target prices from RiskSpec
│   │   │   ├── backtest_engine.py                  # run(df, strategy, cash)
│   │   │   ├── bar_frame_converter.py              # Bars ↔ DataFrame
│   │   │   ├── timeframe_bar_merger.py             # Merge informative columns into primary
│   │   │   ├── condition_tree_visitor.py           # Traverse condition trees
│   │   │   ├── indicator_calculator.py             # Compute technical indicators
│   │   │   ├── indicator_capability_provider.py    # Supported indicator metadata
│   │   │   ├── indicator_job_manager.py           # Async enrichment job lifecycle
│   │   │   ├── indicator_job_runner.py            # Execute enrichment work
│   │   │   ├── indicator_artifact_provider.py     # Read completed artifact bars
│   │   │   ├── optimization_job_manager.py         # Async optimization job lifecycle
│   │   │   ├── optimization_job_runner.py          # Execute optimization work
│   │   │   ├── stock_data_fetcher.py               # Fetch OHLCV from source
│   │   │   ├── price_cache_repository.py           # Cached bar queries
│   │   │   └── symbol_info_repository.py           # Symbol metadata queries
│   │   └── services/       # Pure domain services
│   │       ├── backtest_metrics.py  # Sharpe, Sortino, drawdown, Calmar, etc.
│   │       └── proxy_indicator.py   # Proxy indicator calculation
│   ├── application/
│   │   ├── dto/             # Data crossing layer boundaries (~25 DTOs)
│   │   │   ├── backtest_result.py                     # Full backtest output
│   │   │   ├── backtest_strategy_definition_*.py       # JSON backtest request/result
│   │   │   ├── save_strategy_definition_*.py           # Save request/result
│   │   │   ├── delete_strategy_definition_*.py         # Delete request/result
│   │   │   ├── apply_strategy_features_*.py            # Feature enrichment
│   │   │   ├── apply_indicators_*.py                   # Indicator enrichment
│   │   │   ├── fetch_prices_*.py                       # Price fetch
│   │   │   ├── start_indicator_job_request.py          # Indicator job start
│   │   │   ├── indicator_job_progress_result.py       # Enrichment progress
│   │   │   ├── indicator_job_results_result.py        # Paginated bars
│   │   │   ├── start_optimization_job_request.py       # Optimization job start
│   │   │   ├── optimization_job_progress_result.py     # Optimization progress
│   │   │   ├── optimization_job_results_result.py      # Ranked results
│   │   │   ├── backtest_request.py                     # Named strategy backtest
│   │   │   └── cached_prices_result.py                 # Cached query output
│   │   ├── services/        # Application-level orchestration
│   │   │   ├── strategy_definition_parser.py     # Main parser (implements domain ABC)
│   │   │   ├── strategy_definition_serializer.py # Canonical → JSON dict
│   │   │   ├── strategy_condition_parser.py      # Side rule condition trees
│   │   │   ├── strategy_condition_group_parser.py # Nested all/any/not groups
│   │   │   ├── strategy_operand_parser.py         # Operand normalization
│   │   │   ├── strategy_parameter_resolver.py     # Defaults + overrides + validation
│   │   │   ├── strategy_indicator_resolver.py     # Alias → concrete column + fallback
│   │   │   ├── strategy_feature_resolver.py       # Feature declarations
│   │   │   ├── strategy_risk_resolver.py          # Risk block + param ref resolution
│   │   │   ├── strategy_timeframe_resolver.py     # Timeframe declarations
│   │   │   ├── strategy_capability_service.py     # SDK capability metadata
│   │   │   ├── strategy_schema_provider.py        # JSON Schema
│   │   │   ├── strategy_indicator_catalog.py      # Supported indicator registry
│   │   │   ├── strategy_warning_rule.py           # Warning interface
│   │   │   ├── strategy_limit_rule.py             # Limit interface
│   │   │   ├── required_column_collector.py       # Column requirements (incl. formulas)
│   │   │   ├── feature_input_column_collector.py  # Feature source columns
│   │   │   ├── serialize_group_visitor.py         # Condition tree → dict
│   │   │   └── description_visitor.py             # Condition tree → readable text
│   │   ├── use_cases/       # Orchestration — depends on domain interfaces only
│   │   │   ├── validate_strategy_definition.py
│   │   │   ├── explain_strategy_definition.py
│   │   │   ├── backtest_strategy_definition.py
│   │   │   ├── save_strategy_definition.py
│   │   │   ├── delete_strategy_definition.py
│   │   │   ├── apply_strategy_features.py
│   │   │   ├── apply_indicators.py
│   │   │   ├── start_indicator_job.py
│   │   │   ├── get_indicator_job_progress.py
│   │   │   ├── get_indicator_job_results.py
│   │   │   ├── cancel_indicator_job.py
│   │   │   ├── start_optimization_job.py
│   │   │   ├── get_optimization_job_progress.py
│   │   │   ├── get_optimization_job_results.py
│   │   │   ├── cancel_optimization_job.py
│   │   │   ├── run_backtest.py
│   │   │   ├── fetch_prices.py
│   │   │   ├── query_cached_prices.py
│   │   │   ├── delete_cached_prices.py
│   │   │   ├── get_latest_quote.py
│   │   │   ├── get_symbol_info.py
│   │   │   └── list_cached_symbols.py
│   │   └── backtest_result_mapper.py  # Engine dict → DTO
├── infrastructure/          # Concrete implementations
│   ├── tables/              # SQLAlchemy ORM
│   │   ├── price_bar.py
│   │   ├── strategy_document.py
│   │   ├── symbol_info.py
│   │   └── indicator_artifact.py     # Persisted enriched bars
│   ├── data/                # DB connection (SQLite + WAL)
│   │   └── connection.py
│   ├── repositories/        # SQL implementations
│   │   ├── sql_price_cache_repository.py
│   │   ├── sql_strategy_document_repository.py
│   │   ├── sql_symbol_info_repository.py
│   │   └── sql_indicator_artifact_repository.py
│   └── services/            # Infrastructure services
│       ├── backtest_runner.py                 # Bar-by-bar engine
│       ├── builtin_strategy_provider.py       # Hardcoded strategies
│       ├── composite_strategy_provider.py     # Chain of providers
│       ├── database_strategy_provider.py      # Saved JSON strategies
│       ├── strategy_definition_factory.py     # Compile definition → strategy
│       ├── json_rule_based_strategy.py        # JSON strategy runtime
│       ├── condition_evaluator.py             # Condition tree + fallback evaluation
│       ├── json_risk_price_calculator.py      # Stop/target pricing
│       ├── pandas_strategy_feature_calculator.py  # Feature calculation + formulas
│       ├── pandas_formula_feature_calculator.py   # Formula AST evaluation
│       ├── pandas_bar_frame_converter.py      # Dict ↔ DataFrame
│       ├── pandas_ta_indicator_calculator.py  # Indicators + dynamic period dispatch
│       ├── pandas_timeframe_bar_merger.py     # Multi-timeframe merge
│       ├── bar_merger.py                      # Core merge logic
│       ├── cached_price_indicator_job_runner.py  # Enrichment execution
│       ├── in_memory_indicator_job_manager.py    # Job + artifact store (SQLite-backed)
│       ├── grid_search_optimizer.py           # Grid/random parameter search
│       ├── in_memory_optimization_job_manager.py  # Optimization job store
│       ├── fetch_job.py / fetch_job_manager.py    # Async fetch
│       ├── yfinance_stock_fetcher.py          # yfinance API
│       ├── hyperliquid_fetcher.py             # Hyperliquid API
│       └── rate_limiter.py / hyperliquid_rate_limiter.py
│   └── backtest_strategies/  # Built-in strategies
│       ├── sma_crossover.py
│       ├── rsi_mean_reversion.py
│       ├── momentum_breakout.py
│       └── auction_drive.py
├── presentation/
│   ├── api/                 # FastAPI routes + Pydantic DTOs
│   └── mcp/                 # FastMCP tools
│       ├── tools/           # symbols, prices, jobs, analysis, strategy_json,
│       │                     #   indicators, optimization
│       └── presenters/      # Response formatting
├── startup/                 # Composition root — wires everything
│   ├── bootstrap.py         # DB init + logging + table registration
│   ├── service_factory.py   # All factories, lazy singletons, DI wiring
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

### Behavioral

| Pattern | Where | Why |
|---------|-------|-----|
| **Strategy** | `TradingStrategy` ABC → 4 built-ins + `JsonRuleBasedStrategy` | Swappable strategy logic |
| **Strategy** | `RiskPriceCalculator`, `StrategyFeatureCalculator`, `FormulaFeatureCalculator` | Pluggable calculation |
| **Strategy** | `StockDataFetcher` → `YFinanceFetcher`, `HyperliquidFetcher` | Swappable data sources |
| **Template Method** | `BacktestRunner.run()` | Fixed engine loop, strategy varies |
| **Visitor** | `ConditionTreeVisitor` → 4 collectors/visitors | Tree walks share interface |
| **Chain of Responsibility** | `CompositeStrategyProvider` + fallback indicator evaluation | Try providers/sources in order |
| **Observer** | `FetchJob`, `EnrichmentJob`, `OptimizationJob` + async managers | Pollable background work |
| **Pipeline** | Multi-step parser: params → timeframes → indicators → features → risk → conditions | StrategyDefinitionParser |
| **Registry** | `_DYNAMIC_HANDLERS`, `_INDICATOR_HANDLERS`, `_FEATURE_HANDLERS` | Extensible indicator/feature dispatch |

### Creational

| Pattern | Where | Why |
|---------|-------|-----|
| **Factory** | `startup/service_factory.py` — all `_make_*` / `_get_*` functions | Composition root |
| **Factory** | `StrategyDefinitionFactory` | Compile JSON → `TradingStrategy` |
| **Builder** | `result_dto_from_raw()` | Engine dict → `BacktestResultDTO` |

### Structural

| Pattern | Where | Why |
|---------|-------|-----|
| **Repository** | `PriceCacheRepository`, `StrategyDocumentRepository`, `EnrichmentArtifactRepository` → SQLite | DB behind interfaces |
| **DTO** | `core/application/dto/` — ~25 DTOs | Layer boundary |
| **Presenter** | `StrategyJsonPresenter` | MCP response formatting |
| **Facade** | `StrategyDefinitionParser` — single `parse()` | Complex parsing behind one call |
| **Dependency Injection** | Constructor injection everywhere | Testable, no hidden state |

## Data Flows

### Agent strategy workflow

```
Agent
  → get_strategy_capabilities        (discover operators, indicators, features)
  → validate_strategy_definition     (check schema + semantics, JSON or YAML)
  → explain_strategy_definition       (verify with human-readable text)
  → fetch_price_history               (async, rate-limited, pass start_date!)
  → compute_indicators                (server-side, no payload limits)
  → get_indicator_job_results         (page enriched bars)
  → backtest_strategy_definition      (bars_artifact_id — no large JSON)
  → start_optimization_job            (grid/random search over params)
  → save_strategy_definition          (persist validated strategy)
```

### Multi-timeframe workflow

```
Agent
  → validate_strategy_definition → get primary + informative required indicators
  → compute_indicators(symbol, interval="1h", timeframe_alias="primary")
  → compute_indicators(symbol, interval="1d", timeframe_alias="daily")
  → backtest_strategy_definition(
      bars_artifact_id="<primary_id>",
      informative_bars_artifact_ids_json='{"daily":"<daily_id>"}'
    )
  → start_optimization_job(... same artifact IDs ...)
```

### Indicator job flow

```
compute_indicators → job_id
  → Background: load cached bars → compute indicators → compute features
  → Store bars in SQLite (survives restart)
  → get_indicator_job_results(job_id, page, page_size)
```

### Optimization job flow

```
start_optimization_job(bars_artifact_id, param_ranges, metric)
  → For each param combination:
      → Validate strategy with overrides
      → Resolve artifacts → merge timeframes if needed
      → Backtest → collect metrics
  → Rank by metric → return all results
```

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

## Database Schema (SQLite)

```sql
CREATE TABLE price_bar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL, source TEXT NOT NULL, interval TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    open REAL NOT NULL, high REAL NOT NULL,
    low REAL NOT NULL, close REAL NOT NULL, volume INTEGER,
    UNIQUE(symbol, source, interval, timestamp)
);

CREATE TABLE symbol_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT UNIQUE NOT NULL,
    company_name TEXT, sector TEXT, industry TEXT,
    exchange TEXT, market_cap REAL, fetched_at TEXT
);

CREATE TABLE strategy_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '2.0',
    description TEXT,
    definition_json TEXT NOT NULL,
    normalized_json TEXT,
    tags_json TEXT DEFAULT '[]',
    created_at TEXT, updated_at TEXT
);

CREATE TABLE indicator_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    symbol TEXT NOT NULL, source TEXT NOT NULL, interval TEXT NOT NULL,
    mode TEXT NOT NULL, timeframe_alias TEXT NOT NULL DEFAULT 'primary',
    status TEXT NOT NULL DEFAULT 'completed',
    bars_json TEXT NOT NULL,
    total_bar_count INTEGER NOT NULL DEFAULT 0,
    indicators_applied_json TEXT DEFAULT '[]',
    features_applied_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);
```

## Two Data Sources

| | yfinance | Hyperliquid |
|---|---------|-------------|
| Rate limiter | Sliding window (30 req/min) | Token bucket (1200 weight/min) |
| Symbols | Stock tickers (AAPL, TSLA) | Plain (BTC, PURR) or dex:COIN (flx:TSLA) |
| Full history | `period="max"` | Chunked backwards until empty |
| SDK | `yfinance` | `hyperliquid-python-sdk` |
