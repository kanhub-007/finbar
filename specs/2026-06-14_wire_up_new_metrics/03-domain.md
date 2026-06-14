# Domain Model — Integrate New Market Metrics

## Ubiquitous Language (Glossary)

Every domain term, defined in one sentence. Synonyms merged, homonyms split.

| Term | Definition | Synonyms (merge) | Homonyms (split) |
|------|-----------|------------------|------------------|
| Metric | A named, computable market quantity (e.g. `corwin_schultz_spread`) | indicator | Not: "performance metric" (Sharpe, drawdown) |
| Metric Name | The canonical string identifier used in YAML, MCP, and API | column name, indicator name | — |
| Calculator | A pure domain function in `domain/services/` computing a Series/scalar from OHLCV | domain function | Not: handler (the adapter) |
| Handler | A thin adapter registered with `@_register` that reads DataFrame columns, calls a Calculator, writes the result column | indicator handler | — |
| Unified Catalog | The single source of truth: validates names for the parser AND answers capability questions | MetricCatalog | (replaces the former two-catalog split) |
| Dispatcher | `PandasTaIndicatorCalculator` — maps a metric name to its handler and executes it | calculator engine | — |
| Resolution Path | One concrete way to compute a conceptual metric, ordered by confidence | compute path | — |
| Dual-path Resolution | `resolve_best()` — auto-selects the highest-confidence path whose data is satisfied | path selection | — |
| Confidence Level | How close a computed value is to ground truth: `actual`, `approximation`, `proxy`, `unavailable` | quality tier | — |
| Derivatives Metric | A metric sourced from CoinGlass/Hyperliquid derivatives data (funding, OI, CVD, liquidations) | derivatives data | Not: an OHLCV-computed proxy |
| Derivatives Merge | The no-lookahead as-of join of persisted derivatives rows onto OHLCV bars | derivatives enrichment | — |
| Data Class | What data is available: `daily_ohlcv`, `intraday_ohlcv`, `external_provider` | data mode | — |

## Concept Taxonomy

| Concept | Classification | Why |
|---------|---------------|-----|
| Metric Name | Value Object | Immutable string; identity is the string |
| Calculator (pure function) | Domain Service | Stateless operation on Series/DataFrame inputs |
| Handler | Infrastructure Service | Adapter bridging pure function ↔ DataFrame pipeline |
| `UnifiedMetricCatalog` | Domain Service | Stateless registry: validates names + answers capability |
| `MarketMetricDefinition` | Entity (frozen) | Has identity (name), attributes; immutable |
| `MetricResolutionPath` | Value Object | Defined entirely by attributes |
| `MetricCapabilityResult` | Value Object (mutable) | Result DTO; no identity |
| `PandasTaIndicatorCalculator` | Infrastructure Service | Orchestrates handlers on a DataFrame |
| `DerivativesMetrics` | Entity | Has identity (symbol+timestamp), persisted, lifecycle |
| `DerivativesDataProvider` | Interface (domain) | ABC for CoinGlass/Hyperliquid clients |
| `DerivativesRepository` | Interface (domain) | ABC for persistence |

## Relationships

| From | Relationship | To | Cardinality |
|------|-------------|-----|-------------|
| Strategy YAML | references | Metric Name | 1:N |
| Metric Name | resolved-by | UnifiedMetricCatalog | 1:1 |
| Metric Name | dispatched-by | Handler | 1:1 |
| Handler | wraps | Calculator | 1:1 |
| Conceptual Metric | has | Resolution Path | 1:N |
| `UnifiedMetricCatalog` | contains | `MarketMetricDefinition` | 1:N (~110) |
| `MarketMetricDefinition` | lists | `MetricResolutionPath` | 1:N (0 for simple, 2-3 for dual-path) |
| OHLCV DataFrame | enriched-by | Handler output | 1:N |
| OHLCV DataFrame | merged-with | Derivatives data | N:1 (one series per metric) |
| Derivatives Metric | sourced-from | DerivativesDataProvider | N:1 |

## Entities

| Entity | Fields | Behaviour | Persisted? |
|--------|--------|-----------|------------|
| MarketMetricDefinition | name, family, description, required_data_classes, required_columns, min_lookback, confidence, resolution_paths, implemented, proxy_candidates, required_providers | (frozen dataclass — no behaviour) | No (static in code) |
| DerivativesMetrics | symbol, timestamp, open_interest, funding_rate, liquidations_*, long_short_ratio, cvd, interval | (frozen dataclass) | Yes (CoinGlassData ORM table) |

## Value Objects

| Value Object | Fields | Used where |
|-------------|--------|------------|
| MetricResolutionPath | metric_name, required_data_class, required_columns, confidence, priority, interval_min | MarketMetricDefinition.resolution_paths |
| MetricCapabilityResult | metric, supported, computable, confidence, selected_metric, available_paths, missing_data_classes, missing_providers, warnings | check() / resolve_best() return value |
| Metric Name (str) | the canonical name | everywhere |

## Domain Events

No new domain events in this spec. Derivatives fetching reuses the existing
`FetchDerivativesUseCase` which returns a result DTO (no event bus).

## Interfaces (for DI / Repository pattern)

### Existing interfaces (no changes)

| Interface | Methods | Implemented by |
|-----------|---------|----------------|
| `DerivativesDataProvider` | fetch(), fetch_cvd(), fetch_open_interest() | CoinGlassClient |
| `DerivativesRepository` | save(), save_batch(), find(), latest() | SqlCoinGlassRepository |
| `IndicatorCalculator` | calculate(df, indicators) | PandasTaIndicatorCalculator |
| `IndicatorCapabilityProvider` | resolve(), supports_concrete(), accepts_period() | UnifiedMetricCatalog |

### New interface methods

| Interface | New methods | Why |
|-----------|-------------|-----|
| `DerivativesDataProvider` | `fetch_liquidations()`, `fetch_long_short_ratio()` | Unlock liquidations + L/S ratio metrics |
| `HyperliquidFetcher` (concrete) | `fetch_funding_history()` | Free funding-rate source (no API key) |

### New concrete method (not on an interface)

| Method | On class | Why |
|--------|---------|-----|
| `all_metric_names() -> set[str]` | `UnifiedMetricCatalog` (concrete, not interface) | Name-sync test (Scenario 1.3) needs to enumerate all catalogued names. Not on either ABC because it's a test-only helper. |

### `DataClass` enum location

String values like `"daily_ohlcv"`, `"intraday_ohlcv"` must match the
`DataClass` enum at
`finbar_strategy_runtime/domain/entities/data_class.py`. Always import
`DataClass` and use the enum members in code — never bare strings.

## Invariants (Always-True Rules)

These are the physics of the system — they constrain every scenario.

| # | Invariant | Enforcement point |
|---|-----------|-------------------|
| 1 | **Name-sync:** A name accepted by the parser MUST have a registered handler, OR the catalog MUST report `computable=False`. Never accept a name that silently produces no column. | Both catalog and dispatch table populated from one source of truth; scenario 1.3 verifies set agreement |
| 2 | **No silent NaN:** If a handler fails or inputs are missing, the column is all-NaN (not absent). Strategies referencing it get `None` → condition False, not a crash. | Handler wrapper: `try/except → NaN Series`; scenarios 2.2, 2.3 |
| 3 | **No lookahead in derivatives merge:** A derivatives value timestamped T is only visible to bars at T+1 or later. | `merge_derivatives_asof` uses `availability = timestamp + interval_offset`; scenario 5.1 |
| 4 | **Confidence honesty:** `check()` returns `computable=True` only when a handler is registered AND data is available. The `implemented` flag matches handler reality. | Unified catalog cross-references handler registry; scenarios 1.1, 1.3, 5.3 |
| 5 | **OHLCV purity:** OHLCV-based calculators never make network/DB calls. Derivatives data is pre-merged before calculators run. | Layer boundary: handlers in indicators/, calculators in domain/services/ |
| 6 | **Derivatives require persistence:** A derivatives metric is computable only if its data was fetched and stored. Missing data → `computable=False` with a clear message. | Catalog checks the repository; scenario 5.3 |

## Entity Lifecycles

**Metric Definition (design-time, static):**
```
[catalogued] → implemented=False (no handler, not computable)
            → implemented=True (handler registered) → computable depends on data class
```

**Derivatives data (runtime):**
```
[not fetched] → fetched (via fetch_derivatives) → persisted (DB row)
            → merged (as-of join onto OHLCV frame) → consumed (strategy reads column)
```

**Derivatives metric computability:**
```
[unknown name]                    → supported=False
[known, no data in DB]            → supported=True, computable=False, hint "run fetch_derivatives"
[known, data in DB for timeframe] → supported=True, computable=True
```

## Entity vs ORM separation

- **Domain entity:** `DerivativesMetrics` (pure frozen dataclass, `core/domain/entities/derivatives_metrics.py`)
- **ORM model:** `CoinGlassData` (`infrastructure/tables/coinglass_data.py`)
- **Mapper:** `_domain_to_orm` / `_orm_to_domain` in `sql_coinglass_repository.py`

Market metric definitions have **no ORM model** — they are static data in code
(`UnifiedMetricCatalog._METRICS`). No persistence needed.
