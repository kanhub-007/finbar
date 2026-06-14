# Integrate New Market Metrics into Strategy Pipeline

## User Story

**As a** strategy developer (human or AI agent),
**I want to** reference any of the ~90 new metric calculators (Fibonacci
retracements, SMC order blocks, VSA no-demand, Corwin-Schultz spread, Amihud
illiquidity, Hyperliquid funding rate) by name in my strategy YAML, MCP call,
or API request,
**so that** I can backtest and run strategies using the full metric catalog —
and can *discover* (via MCP/API) which metrics are computable for any given
symbol + source, which are proxies, and which need data I don't have.

## Context

The `finbar_strategy_runtime` package contains ~90 pure domain-service functions
(microstructure proxies + price-action calculators) and a
`StaticMarketMetricCatalog` with ~110 metric definitions and dual-path
resolution. These were built and tested in the prior spec
(`2026-06-14_extended-market-metrics-data`) but never wired into the actual
strategy pipeline.

There are three disconnected layers:

1. **Parser whitelist** (`StrategyIndicatorCatalog._FIXED`) — a dict that lists
   which metric names the strategy YAML parser will accept. It currently has 0
   of the new names. An unknown operand produces a `unknown_operand` validation
   error.

2. **Compute dispatcher** (`PandasTaIndicatorCalculator._INDICATOR_HANDLERS`) —
   a dispatch table mapping each metric name to a handler function via the
   `@_register` decorator. No handlers exist for the new metrics.

3. **Discovery surface** — MCP tools (`compute_indicators`,
   `compute_trading_metrics`) and API routes (`/indicators/jobs`) call the same
   dispatcher. `StaticMarketMetricCatalog` (capability checks, dual-path
   resolution) is imported nowhere outside tests.

Separately, a **CoinGlass derivatives stack** already exists
(`CoinGlassClient`, `DerivativesMetrics` entity, `SqlCoinGlassRepository`,
`FetchDerivativesUseCase`, `fetch_derivatives` MCP tool) with historical
endpoints for funding, CVD, and open interest. But:
- It is not merged into the OHLCV bar frame that strategies read.
- Two CoinGlass endpoints (liquidations, long/short ratio) are not implemented
  even though the entity/ORM fields exist.
- Hyperliquid's free `funding_history` endpoint (no API key) is not wired.

This spec connects all layers and exposes the catalog via MCP/API.

## Non-Goals

These are explicitly NOT being built in this spec:

- **Live polling of derivatives data.** Backtests need historical series; the
  CoinGlass `aggregated-history` endpoints supply them. Live polling/websocket
  collectors are out of scope.
- **VIX, put/call ratio, COT, sentiment metrics.** No data source exists for
  these (crypto markets have no native VIX; Hyperliquid is perps-only so no
  options). They stay catalogued as `computable=False`.
- **Elliott Wave detection engine.** The 5 Elliott Wave catalog entries stay
  `implemented=False` — they need a dedicated wave-detection engine beyond
  this spec's scope.
- **L1 blockchain parsing for Hyperliquid liquidations.** The Hyperliquid SDK
  has no market-wide liquidations endpoint; L1 parsing is far out of scope.
  Liquidations come from CoinGlass instead.
- **New indicator math.** All calculators exist and are tested. This spec is
  pure integration/wiring — no new math.
- **Cross-asset metrics (information_share family).** The 5 functions
  (`cross_price_leadership`, `volume_weighted_is`, `opening_price_leadership`,
  `daily_cross_correlation`, `daily_beta_ols`) need a benchmark asset's price
  series. The dispatcher has no benchmark concept. They are marked
  `implemented=False` and deferred to a future cross-asset spec.
- **`turnover` metric.** Needs `shares_outstanding` which has no data source
  in the OHLCV pipeline. Marked `implemented=False`.
- **Merging the `finbar/` mirror into the package.** The package
  (`packages/strategy-runtime/`) is the source of truth; `finbar/` re-exports
  are thin shims. We extend the package; the shims follow automatically.
