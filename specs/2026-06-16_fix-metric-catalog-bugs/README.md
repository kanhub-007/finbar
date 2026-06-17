# Fix Metric Catalog Bugs

**Date:** 2026-06-16
**Cynefin:** Complicated — cause and effect exists but requires expertise in the handler dispatch system, pandas_ta dependency resolution, and rolling_scalar_wrapper mechanics.

## Why (Root Cause)

The metric catalog documents ~200+ indicators, but ~25 return null, produce no output, or lie about their computability. This creates a trust gap: users request metrics that `check_metric` says are computable, backtests silently produce wrong results, and the catalog documentation diverges from runtime behavior.

**Five Whys:**
1. Why do metrics return null? → Handler arg mismatches, window/lookback disagreements, missing data columns.
2. Why are there arg mismatches? → No compile-time check between handler decorator args and function signatures.
3. Why no compile-time check? → Python dynamic dispatch; handlers are registered via decorator, no type-level enforcement.
4. Why no runtime validation? → `check_metric` only checks handler existence + OHLCV column presence, not execution correctness.
5. Why was this not caught earlier? → No smoke-test pipeline that exercises every metric against real data.

**Fundamental truths:**
- Every handler in `_INDICATOR_HANDLERS` maps to a function that expects specific columns and parameters
- `rolling_scalar_series` applies a calculator with a window that must match the calculator's internal lookback
- `enrich_dataframe_with_proxies` returns `df.copy()` — losing in-place mutations from other handlers
- Some metrics require data that data sources don't provide (`opening_volume`, `closing_volume`)
- Some metrics require more bars than a typical test query provides (hurst: 100, market_regime: 220)

## What (Summary)

Fix 14 confirmed bugs across 4 root cause categories, update catalog documentation for 11 conditional/limited metrics, and enhance `check_metric` to prevent future regressions.

## Key Decisions

| Decision | Rationale | Alternative rejected |
|----------|-----------|---------------------|
| Fix bugs first, enhance tooling second | P0 bugs silently corrupt backtest results | Rewriting dispatch system — too risky |
| Compute missing proxies inside `enrich_dataframe_with_proxies` (Option B) | Proxy handlers are never dispatched due to `name.startswith("proxy_")` short-circuit; the enrichment function is the only real path | Removing the short-circuit (Option A) — more work, no benefit |
| Delete dead proxy handlers in `inside_bar.py` | They only make `check_metric` lie about computability | Keep them as documentation — misleading |
| Surface handler exceptions in job metadata | Silent `except Exception: NaN` is why all bugs went undetected | Promote to hard errors — one bad metric shouldn't abort the whole job |
| Compose window sizes from calculator defaults | Avoids wrapper-function disagreement forever | Manually set every window — fragile |
| Implement proxy for `first_last_hour_vol_fraction` | Keep metric alive with meaningful data | Remove from catalog — loses value |
| Smoke-test via `check_metric` enhancement | Catches regressions before user sees them | Separate CI smoke pipeline — higher effort |

## Links

- [User Story & Context](01-story.md)
- [Scenarios](02-scenarios.md)
- [Domain Model](03-domain.md)
- [Implementation Guide](04-implementation.md)
- [Architecture Decisions](05-architecture.md)
- ⚠️ [Verification & Corrections](../../research/03-verification-and-corrections.md) — **read this**; it corrects the proxy root cause and adds the observability finding
