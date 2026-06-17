# Unify Proxy Indicator Dispatch

## User Story

As a **strategy-runtime maintainer**, I want `proxy_*` indicators to
dispatch through the normal handler registry — one handler per metric,
returning only the requested column — so that proxy metrics obey the
same "handler presence = computability" invariant as every other
metric, request scope is predictable, and the streaming calculator
can treat proxies uniformly.

## Context

Today the proxy family is an architectural exception with four
symptoms, all caused by one short-circuit in
`pandas_ta_indicator_calculator.py`:

```python
for name in indicators:
    if name.startswith("proxy_"):           # ← short-circuit
        result = _compute_proxies(result, cache)   # computes ALL 12
    elif name in _INDICATOR_HANDLERS:
        ...
```

`_compute_proxies()` calls `enrich_dataframe_with_proxies(df)`, which
returns a copy with **all 12 proxy columns** regardless of what was
requested. The 9 `@_register("proxy_*")` handlers in
`inside_bar.py` are dead code — they populate
`_INDICATOR_HANDLERS` (so `check_metric` recognises the names) but are
never invoked.

This was a deliberate expedient (ADR-2 of the 2026-06-16 metric-catalog
spec chose Option B: fix the proxies inside `enrich_dataframe_with_proxies`,
defer the dispatch unification). That decision was correct *for that
spec* — it fixed the null-output bugs with a ~10-line change. But it
left four loose ends:

1. **Surprising request scope.** `calc.calculate(df, ["proxy_vwap"])`
   silently returns all 12 proxy columns. A strategy that reads a proxy
   column it didn't request "works" by accident; tightening it later is
   a silent break. (Confirmed unwanted — see discussion.)
2. **Invariant violation.** The catalog's central invariant — "a
   catalogued metric is computable iff it has a registered handler, and
   the handler is what runs" — does not hold for proxies. `proxy_atr`
   reports `computable=True` via the dead handler, but the dead handler
   never runs.
3. **3 undocumented proxies.** `enrich_dataframe_with_proxies` emits
   `proxy_typical_price`, `proxy_ohlc4`, and `proxy_iv`, but none are
   registered as handlers or in the parser whitelist. They are
   undiscoverable side-effects of requesting any other proxy.
4. **Blocks clean streaming.** The streaming-indicator-calculator spec
   (2026-06-16) classifies names via `_handler_registry` and its windowed
   fallback reuses per-name batch handlers. For proxies there is no
   per-name batch handler today — only the monolithic
   `enrich_dataframe_with_proxies`. So under the streaming spec's
   windowed-default rule, a `proxy_*` name would resolve to `UNKNOWN`
   and **raise at engine construction** (fail-closed). This spec makes
   each proxy a real registered handler with a `min_lookback`, so the
   windowed-default rule covers it.

## Non-Goals

- **Changing any proxy's formula.** The math in
  `proxy_indicator.py` is correct and validated; this spec moves where
  it runs, not what it computes.
- **Changing the batch `IndicatorCalculator` interface.**
  `calculate(df, indicators) -> df` is unchanged; only the internal
  dispatch routing for `proxy_*` names changes.
- **Implementing streaming proxies.** That belongs to the
  streaming-indicator-calculator spec. This spec only removes the
  architectural wart that would make streaming proxies awkward.
- **Auto-resolving transitive `requires`.** If `proxy_ib_high` declared
  `requires={"proxy_atr"}`, the dispatch would write NaN when
  `proxy_atr` isn't co-requested (same class as `vol_buffer_high`).
  This spec explicitly avoids that by making each handler
  self-contained via a shared compute-if-absent helper (ADR-3).
- **Removing `enrich_dataframe_with_proxies`.** It stays as the
  single-bar enrichment path (`enrich_bar_with_proxies` uses it) and as
  a batch convenience; it just comes off the calculator dispatch hot
  path.
