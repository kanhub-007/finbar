# Finbar Architecture

Strict clean architecture per AGENTS.md — four layers plus a composition root.
Dependencies flow inward. One class per file enforced mechanically (168 classes,
zero multi-class files in `finbar/`).

## Layer Map

```
finbar/
├── core/
│   ├── domain/
│   │   ├── entities/        # Frozen dataclasses — no frameworks
│   │   │   ├── strategy_definition.py   # Parsed strategy (parameters, indicators,
│   │   │   │                             #   features, risk, sides)
│   │   │   ├── strategy_document.py     # Persisted JSON strategy with metadata
│   │   │   ├── condition.py             # Atomic condition (left op right)
│   │   │   ├── condition_group.py       # Nested all/any/not group
│   │   │   ├── operand.py              # Typed value (field, indicator, feature,
│   │   │   │                             #   param, literal)
│   │   │   ├── indicator_spec.py       # Strategy-local alias → concrete column
│   │   │   ├── feature_spec.py         # Derived feature declaration
│   │   │   ├── risk_spec.py            # Stop-loss / take-profit settings
│   │   │   ├── side_rules.py           # Entry + exit conditions per side
│   │   │   ├── strategy_parameter.py   # Typed runtime parameter
│   │   │   ├── strategy_meta.py        # Strategy metadata for discovery
│   │   │   ├── strategy_kind.py        # BUILTIN / USER_DEFINED enum
│   │   │   ├── strategy_validation_error.py  # Path-specific diagnostic
│   │   │   ├── strategy_validation_result.py # Parse/validate output
│   │   │   ├── signal_result.py        # Bar-by-bar trading signal
│   │   │   ├── price_bar.py            # OHLCV + timestamp
│   │   │   ├── data_source.py          # yfinance / hyperliquid enum
│   │   │   ├── data_mode.py            # REAL / PROXY enum
│   │   │   ├── interval.py             # Bar interval value object
│   │   │   └── symbol_info.py          # Company/asset metadata
│   │   ├── interfaces/     # ABCs — contracts for outer layers
│   │   │   ├── trading_strategy.py              # on_bar(), on_reset(), meta()
│   │   │   ├── strategy_provider.py              # create(), list_metadata()
│   │   │   ├── strategy_definition_strategy_factory.py  # compile definition → strategy
│   │   │   ├── strategy_document_repository.py   # CRUD for saved strategies
│   │   │   ├── strategy_definition_parser.py      # Parse JSON → domain entities
│   │   │   ├── strategy_feature_calculator.py      # Calculate derived features
│   │   │   ├── risk_price_calculator.py            # Stop/target prices from RiskSpec
│   │   │   ├── backtest_engine.py                  # run(df, strategy, cash)
│   │   │   ├── bar_frame_converter.py              # Bars ↔ DataFrame
│   │   │   ├── condition_tree_visitor.py           # Traverse condition trees
│   │   │   ├── indicator_calculator.py             # Compute technical indicators
│   │   │   ├── indicator_capability_provider.py    # Supported indicator metadata
│   │   │   ├── stock_data_fetcher.py               # Fetch OHLCV from source
│   │   │   ├── price_cache_repository.py           # Cached bar queries
│   │   │   └── symbol_info_repository.py           # Symbol metadata queries
│   │   └── services/       # Pure domain services
│   │       ├── backtest_metrics.py  # Sharpe, Sortino, drawdown, Calmar, etc.
│   │       └── proxy_indicator.py   # Proxy indicator calculation
│   ├── application/
│   │   ├── dto/             # Data crossing layer boundaries
│   │   │   ├── backtest_result.py                     # Full backtest output
│   │   │   ├── backtest_strategy_definition_*.py       # JSON backtest request/result
│   │   │   ├── save_strategy_definition_*.py           # Save request/result
│   │   │   ├── delete_strategy_definition_*.py         # Delete request/result
│   │   │   ├── apply_strategy_features_*.py            # Feature enrichment request/result
│   │   │   ├── apply_indicators_*.py                   # Indicator enrichment
│   │   │   ├── fetch_prices_*.py                       # Price fetch request/result
│   │   │   ├── backtest_request.py                     # Named strategy backtest
│   │   │   └── cached_prices_result.py                 # Cached query output
│   │   ├── services/        # Application-level orchestration
│   │   │   ├── strategy_definition_parser.py     # Main parser (implements domain ABC)
│   │   │   ├── strategy_definition_serializer.py # Canonical → JSON dict
│   │   │   ├── strategy_condition_parser.py      # Side rule condition trees
│   │   │   ├── strategy_condition_group_parser.py # Nested all/any/not groups
│   │   │   ├── strategy_operand_parser.py         # Operand normalization
│   │   │   ├── strategy_parameter_resolver.py     # Defaults + overrides + validation
│   │   │   ├── strategy_indicator_resolver.py     # Alias → concrete column
│   │   │   ├── strategy_feature_resolver.py       # Feature declarations
│   │   │   ├── strategy_risk_resolver.py          # Risk block parsing
│   │   │   ├── strategy_capability_service.py     # SDK capability metadata
│   │   │   ├── strategy_schema_provider.py        # JSON Schema
│   │   │   ├── strategy_indicator_catalog.py      # Supported indicator registry
│   │   │   ├── strategy_warning_rule.py           # Warning interface
│   │   │   ├── strategy_warning_rules.py          # Default warning rules
│   │   │   ├── strategy_limit_rule.py             # Limit interface
│   │   │   ├── strategy_limit_rules.py            # Default limit rules
│   │   │   ├── required_column_collector.py       # Backtest column requirements
│   │   │   ├── feature_input_column_collector.py  # Feature source columns
│   │   │   ├── serialize_group_visitor.py         # Condition tree → dict
│   │   │   ├── description_visitor.py             # Condition tree → readable text
│   │   │   ├── strategy_definition_parse_helpers.py  # Shared parsing utilities
│   │   │   ├── no_exit_warning_rule.py             # Missing exit detection
│   │   │   ├── no_stop_warning_rule.py             # Missing stop detection
│   │   │   ├── max_parameters_limit_rule.py        # Parameter count limit
│   │   │   ├── max_indicators_limit_rule.py        # Indicator count limit
│   │   │   ├── max_features_limit_rule.py          # Feature count limit
│   │   │   └── max_condition_depth_limit_rule.py   # Nesting depth limit
│   │   ├── use_cases/       # Orchestration — depends on domain interfaces only
│   │   │   ├── validate_strategy_definition.py
│   │   │   ├── explain_strategy_definition.py
│   │   │   ├── backtest_strategy_definition.py
│   │   │   ├── save_strategy_definition.py
│   │   │   ├── delete_strategy_definition.py
│   │   │   ├── apply_strategy_features.py
│   │   │   ├── run_backtest.py
│   │   │   ├── apply_indicators.py
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
│   │   └── symbol_info.py
│   ├── data/                # DB connection (SQLite + WAL)
│   │   └── connection.py
│   ├── repositories/        # SQL implementations of domain interfaces
│   │   ├── sql_price_cache_repository.py
│   │   ├── sql_strategy_document_repository.py
│   │   └── sql_symbol_info_repository.py
│   └── services/            # Infrastructure services
│       ├── backtest_runner.py                 # Bar-by-bar engine
│       ├── builtin_strategy_provider.py       # Hardcoded strategies
│       ├── composite_strategy_provider.py     # Chain of providers
│       ├── database_strategy_provider.py      # Saved JSON strategies
│       ├── strategy_definition_factory.py     # Compile definition → strategy
│       ├── json_rule_based_strategy.py        # JSON strategy runtime
│       ├── condition_evaluator.py             # Condition tree evaluation
│       ├── json_risk_price_calculator.py      # Stop/target pricing (registry dispatch)
│       ├── pandas_strategy_feature_calculator.py  # Feature calculation (handler registry)
│       ├── pandas_bar_frame_converter.py      # Dict ↔ DataFrame
│       ├── pandas_ta_indicator_calculator.py  # Technical indicators
│       ├── backtest_position.py               # Position state
│       ├── backtest_loop_state.py             # Loop state (trades, equity, cash)
│       ├── fetch_job.py                       # Async fetch job state
│       ├── fetch_job_manager.py               # In-memory job store
│       ├── yfinance_stock_fetcher.py          # yfinance API
│       ├── hyperliquid_fetcher.py             # Hyperliquid API
│       ├── rate_limiter.py                    # Sliding window rate limit
│       └── hyperliquid_rate_limiter.py        # Token bucket rate limit
│   └── backtest_strategies/  # Built-in strategy implementations
│       ├── sma_crossover.py
│       ├── rsi_mean_reversion.py
│       ├── momentum_breakout.py
│       └── auction_drive.py
├── presentation/
│   ├── api/                 # FastAPI routes + Pydantic DTOs
│   │   ├── routes/          # symbols, prices, jobs, analysis, health
│   │   └── dto/             # Request/response models
│   └── mcp/                 # FastMCP tools
│       ├── tools/           # symbols, prices, jobs, analysis, strategy_json
│       ├── presenters/      # Response formatting (StrategyJsonPresenter)
│       ├── fetch_job.py
│       └── fetch_job_manager.py
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
| **Strategy** | `TradingStrategy` ABC → 4 built-ins + `JsonRuleBasedStrategy` | Swappable strategy logic at runtime |
| **Strategy** | `RiskPriceCalculator` ABC → `JsonRiskPriceCalculator` (handler registry) | Stop/target calculation by type |
| **Strategy** | `StrategyWarningRule` ABC → `NoExitWarningRule`, `NoStopWarningRule` | Inject warnings, OCP for new checks |
| **Strategy** | `StrategyLimitRule` ABC → 4 limit implementations | Inject limits, OCP for new constraints |
| **Strategy** | `StrategyFeatureCalculator` ABC → `PandasStrategyFeatureCalculator` (handler registry) | Feature calculation by type |
| **Strategy** | `StockDataFetcher` ABC → `YFinanceStockFetcher`, `HyperliquidFetcher` | Swappable data sources |
| **Template Method** | `BacktestRunner.run()` — fixed loop skeleton, strategy varies | Backtest engine |
| **Visitor** | `ConditionTreeVisitor` ABC → `RequiredColumnCollector`, `SerializeGroupVisitor`, `DescriptionVisitor`, depth calculation | Four tree walks share one interface |
| **Chain of Responsibility** | `CompositeStrategyProvider` → `BuiltinStrategyProvider` → `DatabaseStrategyProvider` | Strategy resolution tries providers in order |
| **Observer** | `FetchJob` + `FetchJobManager` + `asyncio.to_thread()` | Async fetch with pollable progress |
| **Pipeline** | `parse → resolve params → resolve indicators → resolve features → resolve risk → parse conditions → warn → enforce limits` | StrategyDefinitionParser orchestrates multi-step parsing |

### Creational

| Pattern | Where | Why |
|---------|-------|-----|
| **Factory** | `startup/service_factory.py` — all `_make_*` / `_get_*` functions | Composition root wires dependencies |
| **Factory** | `StrategyDefinitionFactory` — compile parsed definition → `TradingStrategy` | Strategy instantiation |
| **Builder** | `result_dto_from_raw()` — engine dict → `BacktestResultDTO` | Structured result construction |

### Structural

| Pattern | Where | Why |
|---------|-------|-----|
| **Repository** | `PriceCacheRepository`, `SymbolInfoRepository`, `StrategyDocumentRepository` ABCs → SQLite impls | Database access behind interfaces |
| **DTO** | `core/application/dto/` — 15 DTOs | Data crossing layer boundaries |
| **Presenter** | `StrategyJsonPresenter` — format use case results for MCP | Separation of display logic |
| **Facade** | `StrategyDefinitionParser` — single `parse()` behind multi-step pipeline | Agent API simplicity |
| **Dependency Injection** | Constructor injection everywhere | Testable, no hidden state |

## Data Flows

### Agent strategy workflow

```
Agent
  → get_strategy_capabilities        (discover operators, indicators, features)
  → validate_strategy_json           (check schema + semantics)
  → explain_strategy_json             (verify with human-readable text)
  → fetch_price_history / get_cached_prices
  → apply_indicators                 (enrich bars with SMA, RSI, ATR, etc.)
  → apply_strategy_features          (calculate rolling_max, body_pct, etc.)
  → backtest_strategy_json           (run against enriched primary bars)
  → save_strategy_json               (persist if happy)
```

For large datasets, agents can avoid huge enrichment payloads by using async
enrichment jobs:

```
Agent
  → start_enrichment_job            (server-side cached bars → indicators/features)
  → get_enrichment_job_progress     (poll status/stage/progress)
  → get_enrichment_job_results      (page enriched bars when needed)
  → backtest_strategy_json          (run against bars_artifact_id directly)
```

For multi-timeframe strategies, agents fetch and enrich each timeframe
separately, then pass primary bars plus `informative_bars_json`, or pass
`bars_artifact_id` plus `informative_bars_artifact_ids_json`, to
`backtest_strategy_json`. Informative indicator columns are merged into primary
bars with interval suffixes such as `sma_50_1d`.

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

### Backtest engine loop

```
for each bar:
  1. Execute pending entry at open (next-bar conservative)
  2. Check stop-loss / take-profit for open position
  3. Call strategy.on_bar(bar, position) → SignalResult
  4. Execute signal exit (close at bar close)
  5. Queue entry signal for next bar
  6. Track equity (value, drawdown, position, close)
→ Compute metrics (Sharpe, Sortino, drawdown, Calmar, profit factor)
→ Return trades[], equity_curve[], metrics
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
```

## Two Data Sources

| | yfinance | Hyperliquid |
|---|---------|-------------|
| Rate limiter | Sliding window (30 req/min) | Token bucket (1200 weight/min) |
| Symbols | Stock tickers (AAPL, TSLA) | Plain (BTC, PURR) or dex:COIN (flx:TSLA) |
| Full history | `period="max"` | Chunked backwards until empty |
| SDK | `yfinance` | `hyperliquid-python-sdk` |
