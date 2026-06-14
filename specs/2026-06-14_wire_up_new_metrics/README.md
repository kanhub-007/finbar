# Integrate New Market Metrics into Strategy Pipeline

**Date:** 2026-06-14
**Cynefin:** Complicated
**Status:** Ready to implement

## Why (Root Cause)

The new metric calculators (~90 pure domain functions) and the market metric
catalog (~110 definitions with dual-path resolution) are implemented and tested,
but **disconnected** from the strategy pipeline, MCP, and API. A strategy YAML
referencing `fib_618_retrace` or `corwin_schultz_spread` is rejected as an
`unknown_operand`. The work is invisible to users.

Three layers must be connected and kept in sync:

1. **Parser whitelist** (`StrategyIndicatorCatalog`) — accepts/rejects metric names
2. **Compute dispatcher** (`PandasTaIndicatorCalculator`) — maps name → handler
3. **Discovery surface** (MCP/API tools backed by `StaticMarketMetricCatalog`) —
   lets agents/users see what is computable and why

The original metrics spec deliberately scoped only the math and catalog, deferring
this integration layer. This spec closes the gap.

## What (Summary)

Wire all ~90 OHLCV-based metric calculators and 11 derivatives metrics into the
strategy runtime so they are usable in backtests, MCP calls, and API requests.
Merge the two existing catalogs into one unified source of truth. Expose
capability discovery and dual-path resolution via MCP and FastAPI. Add
no-lookahead merging for CoinGlass/Hyperliquid derivatives data (funding rate,
open interest, CVD, liquidations, long/short ratio).

## Key Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Merge `StrategyIndicatorCatalog` + `StaticMarketMetricCatalog` into one unified catalog | Single source of truth for both parser validation and capability checks; eliminates name-mismatch bugs |
| 2 | Rolling-window wrapper for scalar calculators (roll_spread, hurst, etc.) | Strategies need a value per bar; scalars broadcast as constants are useless for trading |
| 3 | No-lookahead as-of merge for derivatives data | Same invariant as `merge_timeframes`; a derivatives value at time T is only visible at bar T+1 |
| 4 | Confidence honesty: catalog never lies about computability | `check()` returns `computable=True` only when a handler is registered AND data is available |
| 5 | CoinGlass is primary derivatives source (needs API key); Hyperliquid funding is free fallback | CoinGlass has all historical endpoints; Hyperliquid provides free funding-rate history |
| 6 | Liquidations via CoinGlass `/api/futures/liquidation/aggregated-history` (confirmed exists); long/short ratio via `/api/futures/global-long-short-account-ratio/history` | Both historical endpoints confirmed available via API probe |
| 7 | Open interest not polled — fetched as historical series via CoinGlass `aggregated-history` | Backtests need historical data, not live polling |
| 8 | Cross-asset metrics (information_share: 5 functions) deferred to a later spec, marked `implemented=False` | They need a second asset's price series; the dispatcher has no benchmark concept |
| 9 | `turnover` metric marked `implemented=False` (needs `shares_outstanding`, no source in OHLCV) | No data source for shares outstanding in the current pipeline |

## Files

- [01-story.md](01-story.md) — User story, context, non-goals
- [02-scenarios.md](02-scenarios.md) — All scenarios with Gherkin + Verify blocks
- [03-domain.md](03-domain.md) — Domain model: entities, interfaces, invariants
- [04-implementation.md](04-implementation.md) — Step-by-step implementation guide
- [05-architecture.md](05-architecture.md) — Architecture Decision Records (ADRs)

## Scope Summary

| Metric Family | Count | Source | Computable? |
|---------------|-------|--------|-------------|
| Microstructure proxies (spread, volatility, liquidity, order flow, etc.) | ~46 | OHLCV | ✅ Yes (turnover deferred — no shares_outstanding source) |
| Price-action (Fibonacci, SMC, VSA, supply/demand, Hurst, regime) | ~51 | OHLCV | ✅ Yes |
| Cross-asset (information_share) | 5 | OHLCV + benchmark | ❌ Deferred (`implemented=False`) |
| Derivatives (funding, OI, CVD, liquidations, long/short ratio) | 11 | CoinGlass / Hyperliquid | ✅ Yes (when data fetched) |
| External unsourceable (VIX, put/call, COT, sentiment) | ~7 | None | ❌ `computable=False` |
| Elliott Wave (catalogued, no engine) | 5 | OHLCV (future) | ❌ `implemented=False` |
