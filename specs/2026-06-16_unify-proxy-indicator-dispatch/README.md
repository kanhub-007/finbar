# Unify Proxy Indicator Dispatch

**Date:** 2026-06-16
**Cynefin:** Complicated — the proxy formulas are correct and validated;
the work is relocating where they run and closing a dispatch special-case.
Risk is contained: the math is untouched, only routing + registry change.

## Why

The `proxy_*` indicator family is an architectural exception: a
`name.startswith("proxy_")` short-circuit routes ALL proxy names to one
monolithic function that returns all 12 columns regardless of request.
The 9 registered proxy handlers are dead code. This causes four problems:

1. **Surprising request scope** — `calc.calculate(df, ["proxy_vwap"])`
   silently returns all 12 proxies.
2. **Invariant violation** — `check_metric("proxy_atr")` reports
   computable via a dead handler that never runs.
3. **3 undocumented proxies** — `proxy_typical_price`, `proxy_ohlc4`,
   `proxy_iv` are emitted but registered nowhere (undiscoverable).
4. **Blocks clean streaming** — the streaming calculator's per-name
   classifier and windowed fallback have no per-proxy handler to call.

This was deliberately deferred by the 2026-06-16 metric-catalog spec
(ADR-2 chose the 10-line Option B fix; Option A — this spec — was noted
as a follow-up). With the immediate bugs fixed, this spec closes the
follow-up.

## What

Remove the short-circuit; give each of the 12 proxies its own real,
self-contained handler that dispatches through the standard path. Share
the ATR computation across the 5 ATR-dependent proxies via the per-call
cache (MACD pattern). Register all 12 in the capability registry so
`check_metric` is honest by construction.

## Key Decisions

| Decision | Rationale | Alternative rejected |
|----------|-----------|---------------------|
| Per-handler dispatch with exact request scope (ADR-1) | "request one get all 12" is unwanted; uniformity with all other metrics | Keep short-circuit + filter by requested set — leaves the special case |
| Keep `enrich_dataframe_with_proxies` alive, off the hot path (ADR-2) | Single-bar enrichment still needs it; formulas stay DRY via shared `compute_proxy_*` fns | Delete it — breaks `enrich_bar_with_proxies` |
| ATR cluster via compute-if-absent cache helper (ADR-3) | Self-contained handlers + no recompute; mirrors MACD; no dispatch change | `requires={"proxy_atr"}` — transitive-dep NaN problem (Non-Goal) |
| Assign hidden proxies to VOLATILITY family (ADR-4) | `proxy_` is a confidence, not a family; no enum churn | New PROXY family — fragments `list_market_metrics` |

## Scope

3 slices, 8 scenarios. Slice 1 = the core unification (Musts). Slice 2 =
docs. No Slice 3 — streaming is a separate spec (ADR-5 notes the
prerequisite dependency).

## Links

- [User Story & Context](01-story.md)
- [Scenarios](02-scenarios.md)
- [Domain Model](03-domain.md)
- [Implementation Guide](04-implementation.md)
- [Architecture Decisions](05-architecture.md)
- Related: [Fix Metric Catalog Bugs](../2026-06-16_fix-metric-catalog-bugs/) —
  its ADR-2 deferred this work (Option A).
- Related: [Streaming Indicator Calculator](../2026-06-16_streaming-indicator-calculator/) —
  this spec is a prerequisite for clean streaming proxy support (ADR-5).
