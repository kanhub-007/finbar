# Domain Model — Metric Catalog Bug Fixes

## Ubiquitous Language (Glossary)

| Term | Definition | Synonyms |
|------|-----------|----------|
| Handler | A function decorated with `@_register` that computes one or more indicator columns on a DataFrame | indicator handler, metric handler |
| Dependency resolver | The dispatch mechanism that determines which handlers to call based on `requires` sets | dispatcher, orchestrator |
| Rolling scalar wrapper | `rolling_scalar_series()` — wraps a scalar-returning calculator to produce a per-bar Series | scalar wrapper |
| Proxy enrichment | `enrich_dataframe_with_proxies()` — batch-computes proxy indicators on a DataFrame copy | proxy batch |
| Warmup period | The initial bars where rolling/parameterized indicators return NaN due to insufficient lookback | burn-in |
| Data class | Categorization of available data: `daily_ohlcv`, `intraday_ohlcv`, `external_provider` | data tier |
| Metric confidence | How a metric is computed: `actual` (direct), `proxy` (OHLCV estimate), `approximation`, `unavailable` | confidence level |

## Entities

| Entity | Fields | Behaviour | Persisted? |
|--------|--------|-----------|------------|
| UnifiedMetricCatalog | handler_registry, metric_definitions | Resolves `check_metric` requests; determines computability | No (built at import) |
| IndicatorJob | job_id, symbol, interval, indicators_applied, status, error | Tracks async indicator computation | Yes (in-memory + DB cache) |

## Value Objects

| Value Object | Fields | Used where |
|-------------|--------|------------|
| MetricCapabilityResult | name, computable, confidence, warnings | `check_metric` response |
| HandlerRegistration | name, func, requires_set | `_INDICATOR_HANDLERS` dict |
| Dispatch short-circuit | The `if name.startswith("proxy_")` branch in `calculate()` routes proxy names away from the handler registry directly to `enrich_dataframe_with_proxies` | `pandas_ta_indicator_calculator.py` |
| MetricDefinition | name, family, description, computable, confidence | `list_market_metrics` response |

## Interfaces (for DI)

| Interface | Methods | Implemented by |
|-----------|---------|----------------|
| `_register` decorator | `_register(name, requires)` → decorator | `_handler_registry.py` |
| Rolling wrapper | `rolling_scalar_series(calculator, series, window)` | `rolling_scalar_wrapper.py` |
| Proxy enrichment | `enrich_dataframe_with_proxies(df)` | `proxy_indicator.py` |

## Invariants (Always-True Rules)

| # | Invariant | Enforcement point |
|---|-----------|-------------------|
| 1 | A handler whose `requires` set is unsatisfied must NOT be dispatched | `_dynamic_dispatch.py` |
| 2 | `rolling_scalar_series` window must be ≥ calculator's internal lookback | Handler registration |
| Invariant #3 | A `proxy_*` metric must be produced by `enrich_dataframe_with_proxies` (the only dispatched path) — handlers in `inside_bar.py` are dead code and must not be relied upon | `pandas_ta_indicator_calculator.py` dispatch |
| 4 | Handler function signature must match caller's argument count | After fix: pass `volume` to zone functions |
| 5 | `check_metric` must not claim computable if required columns (e.g., `opening_volume`) are missing from all available data sources | `unified_metric_catalog.py` |

## Entity vs ORM separation

- **Domain entities:** Pure Python classes in `finbar_strategy_runtime/domain/entities/` — no framework deps.
- **Handler registry:** Runtime dict `_INDICATOR_HANDLERS` populated via `@_register` decorators at import time.
- **Metric catalog:** Built from handler registry + `MetricDefinition` entries in `_metric_registry.py`.
- **No ORM/persistence models** are involved in this fix — all changes are in domain services and indicator handlers.

## Relationships

| From | Relationship | To | Cardinality |
|------|-------------|-----|-------------|
| HandlerRegistration | has | requires_set (column names) | 1:N |
| UnifiedMetricCatalog | reads | HandlerRegistration | 1:N |
| Proxy enrichment handler | calls | enrich_dataframe_with_proxies | N:1 |
| Rolling-scalar handler | calls | rolling_scalar_series | N:1 |
