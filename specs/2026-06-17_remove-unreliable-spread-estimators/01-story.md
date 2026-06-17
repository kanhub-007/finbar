# Remove Unreliable Spread Estimators from Catalog

## User Story

As a **quantitative trader choosing a spread estimator**, I want the catalog to only list indicators that work for single-asset time series, so that I don't waste time on `corwin_schultz_spread`, `abdi_ranaldo_spread`, or `chung_zhang_spread` — all of which return 0.0 for every bar on every asset tested.

## Context

A comprehensive MCP audit (2026-06-17) tested all 5 OHLC-based spread estimators on both ETH-USDC (crypto, 1h) and AAPL (stock, 1d):

| Estimator | ETH Result | AAPL Result | Reliable? |
|-----------|:---:|:---:|:---:|
| `fong_holden_tran_spread` | — | **0.024** | ✅ Always positive by construction |
| `roll_spread` | 0.0 (expected for crypto) | **0.015–0.017** | ✅ Works for stocks |
| `effective_tick_spread` | N/A | N/A | ⚠️ Needs ≥60 bars |
| `lot_zero_return_spread` | N/A | N/A | ⚠️ Needs ≥60 bars |
| `corwin_schultz_spread` | **0.0** | **0.0** | ❌ |
| `abdi_ranaldo_spread` | — | **0.0** | ❌ |
| `chung_zhang_spread` | — | **0.0** | ❌ |

**Root cause:** All three compute an intermediate value (alpha or covariance) that goes negative in trending markets, then clip it to 0 via `.clip(lower=0)`. The formulas are correct per their respective papers, but those papers were designed for **cross-sectional** analysis (averaging estimates across 300–500 stocks). For single-asset time series — which is finbar's entire use case — the clipping produces all-zero output.

We considered fixing the formulas but determined it's not viable: the estimators are fundamentally cross-sectional tools. Using them on a single symbol is like using a market-beta regression with one stock.

The remaining estimators cover the use cases:
- **`fong_holden_tran_spread`**: OHLC-based, always positive, works on any asset
- **`roll_spread`**: Close-based bid-ask bounce estimator, works on stocks
- **`effective_tick_spread`**: Price-clustering estimator, needs 60+ bars
- **`lot_zero_return_spread`**: Zero-return proportion, needs 60+ bars

## Non-Goals

- **Not deleting the domain service functions** — `corwin_schultz_spread()`, `abdi_ranaldo_spread()`, `chung_zhang_spread()` in `spread_proxies.py` stay as pure functions. They're imported directly by `informed_trading_proxies.py` and `resiliency_proxies.py` for internal compound metrics.
- **Not fixing the internal consumers** — `spread_based_pin_proxy` and `resiliency_spread_to_impact` depend on `corwin_schultz_spread` internally. That's a separate investigation.
- **Not removing from strategy JSON parsing** — strategies that already reference these names in saved definitions will still parse (they just won't find a handler). A migration warning is optional.
