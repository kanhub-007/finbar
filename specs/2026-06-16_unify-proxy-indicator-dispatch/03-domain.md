# Domain Model — Unify Proxy Indicator Dispatch

## Ubiquitous Language (Glossary)

| Term | Definition |
|------|-----------|
| Proxy metric | An OHLCV-only approximation of a metric whose true form needs data a daily/intraday source lacks (e.g. `proxy_atr` ≈ ATR from OHLCV; `proxy_vwap` ≈ typical price). All are prefixed `proxy_`. |
| Short-circuit | The `if name.startswith("proxy_")` branch in `PandasTaIndicatorCalculator.calculate()` that routes ALL proxy names to `enrich_dataframe_with_proxies()`. **Removed by this spec.** |
| Dead handler | A `@_register("proxy_*")` function in `inside_bar.py` that populates `_INDICATOR_HANDLERS` but is never invoked by the dispatch. **Replaced by real handlers.** |
| ATR cluster | The 5 proxies that depend on Wilder-RMA ATR: `proxy_atr`, `proxy_ib_high`, `proxy_ib_low`, `proxy_expected_move`, `proxy_iv`. Share computation via the per-call cache. |
| Compute-if-absent helper | `_ensure_proxy_atr(df, cache) -> pd.Series`: returns the cached ATR Series if present, else computes it and caches it. Mirrors the MACD `cache["macd"]` pattern. |

## Entities / Value Objects

No new entities. This spec rearranges existing dispatch; the
`MarketMetricDefinition` (capability registry) and `HandlerRegistration`
(`_INDICATOR_HANDLERS` tuple) value objects are unchanged in shape.

| Existing entity | Change |
|-----------------|--------|
| `HandlerRegistration` | Each `proxy_*` name now maps to a **real** handler that runs, with `requires` = OHLCV columns only (never `atr`) |
| `MarketMetricDefinition` | 12 `proxy_*` entries added to `_metric_registry.METRICS` (3 were missing entirely) |

## Invariants (enforced)

| # | Invariant | Enforcement point |
|---|-----------|-------------------|
| 1 | Request scope is exact: `calculate(df, ["proxy_vwap"])` returns only `proxy_vwap` | `PandasTaIndicatorCalculator.calculate` — no short-circuit; each handler writes only its own column |
| 2 | Every `proxy_*` column is produced by exactly one handler that actually runs | Construction-time `_validate_consistency` (registry ∩ handled names, already exists) |
| 3 | ATR-cluster handlers are self-contained: requesting `proxy_ib_high` alone succeeds | Each calls `_ensure_proxy_atr(df, cache)`; `requires` excludes `atr` |
| 4 | ATR is computed at most once per `calculate()` call when multiple cluster members are requested | `_ensure_proxy_atr` caches under `_PROXY_ATR_CACHE_KEY` in the per-call `cache` dict |
| 5 | No proxy handler depends on request ordering | Proxies read only OHLCV + their own cache entry, never another proxy's output column |

## Relationships

| From | Relationship | To | Cardinality |
|------|-------------|-----|-------------|
| `proxy_atr` handler | writes | `cache[_PROXY_ATR_CACHE_KEY]` | 1:1 |
| `proxy_ib_high/low/expected_move/iv` handlers | read-if-present-else-compute | `cache[_PROXY_ATR_CACHE_KEY]` | N:1 |
| `PandasTaIndicatorCalculator` | passes | per-call `cache` dict to every handler | 1:N (unchanged) |

## Interfaces (for DI)

No new interfaces. The existing `IndicatorCalculator.calculate(df,
indicators)` contract is unchanged; only the internal routing of
`proxy_*` names changes from a special-case branch to the standard
handler path.

## Streaming coupling (cross-spec dependency)

The streaming-indicator-calculator spec (2026-06-16) classifies names
via `_handler_registry` and applies a **windowed-default rule**: any
registered handler not hand-classified as STREAMING falls back to
`WindowedIndicatorState(maxlen=max(min_lookback, MIN_BARS))`.

**Before this spec:** proxies are not registered handlers — the
`name.startswith("proxy_")` short-circuit routes them to
`enrich_dataframe_with_proxies`, which is invisible to the streaming
classifier. A `proxy_*` name would resolve to `UNKNOWN` and raise at
engine construction (fail-closed).

**After this spec:** each `proxy_*` is a normal registered handler with
a `MarketMetricDefinition.min_lookback`. The streaming windowed-default
rule then covers it automatically — proxies become computable under
streaming (correct, `O(window)` per bar), needing no streaming-spec
special-case.

**Optimality note:** proxies like `proxy_vwap = (H+L+C)/3` are trivially
`O(1)`, so the windowed fallback is correct but suboptimal. A future
streaming slice may add hand-written state classes for the cheap
proxies; that is a performance refinement, not a blocker. This spec
neither adds nor requires those.

This spec is therefore a **prerequisite for streaming proxy
correctness** (without it, streaming any proxy crashes at construction),
but does not implement streaming itself.
