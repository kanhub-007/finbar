# Fix Metric Documentation Errors

## User Story

As a **quantitative trader reading Finbar docs**, I want the metric documentation to accurately reflect what each indicator does, what dependencies it requires, and how to interpret its output, so that I don't waste time debugging documentation-vs-implementation mismatches.

## Context

A comprehensive MCP-based audit (2026-06-17, ETH-USDC 1h + AAPL 1d) comparing `docs/METRIC_CATALOG.md`, `docs/QUANTITATIVE_PROXIES.md`, and the actual implementation revealed documentation errors and missing information:

1. **`cumulative_volume_delta` listed twice** — appears in both §10 (Order Flow Proxies) and §18 (Derivatives/CoinGlass). In reality there is one OHLCV-derived handler. The derivatives section should cross-reference, not duplicate.

2. **QUANTITATIVE_PROXIES.md says `proxy_atr` "Requires `atr` indicator"** — the implementation computes `proxy_atr` independently from high/low/close via `ensure_proxy_atr()`. No `atr` companion indicator needed.

3. **Section 19 Proxies compatibility matrix says "N/A" on intraday** — the implementation computes all 12 proxies fine on intraday data. They're just less accurate than the real indicators. "N/A" is misleading; should say "⚠️ Prefer real indicators."

4. **METRIC_CATALOG.md has no dependency information** — users have no way to know that `trend_direction` requires `sma_20` + `sma_50` + `sma_200`, or that `wyckoff_phase` requires `profile_shape`. Every metric table should include a "Requires" column.

5. **Spread estimator reliability not documented** — investigation revealed that `corwin_schultz_spread`, `abdi_ranaldo_spread`, and `chung_zhang_spread` return 0.0 for both crypto (ETH) and stock (AAPL) data due to alpha/covariance clipping in trending markets. Only `fong_holden_tran_spread` and `roll_spread` produce usable estimates for single-asset time series. The docs should guide users to the reliable ones.

Additionally, two behavioral clarifications should be added:
- `hurst_exponent` is a single scalar broadcast, not a rolling window
- `corwin_schultz_spread` and `roll_spread` may return 0.0 for 24/7 crypto markets (expected)

## Non-Goals

Things explicitly NOT being built in this iteration:
- **Code changes** — this is documentation-only; no handler or calculator changes.
- **Adding new metrics** — only clarifying existing ones.
- **Rewriting the entire catalog** — targeted fixes only.
