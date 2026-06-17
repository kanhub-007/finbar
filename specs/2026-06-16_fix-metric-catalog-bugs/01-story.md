# Fix Metric Catalog Bugs

## User Story

As a **quantitative trader using Finbar**, I want every metric the catalog says is computable to actually return real values, so that my backtests produce correct results and I don't waste time debugging silent nulls.

## Context

The Finbar metric catalog documents ~200+ technical indicators, microstructure metrics, and price action signals spanning 21 families. A comprehensive MCP-based audit (2026-06-16, ETH-USD daily + hourly) revealed that ~25 metrics either return all-null output, produce no column at all despite being listed in `indicators_applied`, or report computability incorrectly via `check_metric`.

These bugs fall into four root causes:
1. **Handler argument mismatches** (4 metrics) — handlers pass wrong args to computation functions.
2. **Window/lookback disagreements** (4 metrics) — `rolling_scalar_series` window smaller than function's internal lookback.
3. **Dependency resolution errors** (4 metrics) — proxy handlers depend on wrong indicator name.
4. **Data source limitations** (5 metrics) — metrics need columns/data that yfinance/Hyperliquid don't provide.

Users who rely on these metrics in strategy conditions get silent failures (null-treated-as-false) that produce incorrect backtest results with no error message.

## Non-Goals

Things explicitly NOT being built in this iteration:
- **Rewriting the indicator dispatch system** — the existing handler registry + dependency resolver works for 83% of metrics; a full rewrite is a separate project.
- **Adding new metrics** — this is a fix/polish iteration, not a feature expansion.
- **CoinGlass derivative integration** — the 11 derivatives metrics remain external; adding CoinGlass API key support is out of scope.
- **Performance optimization** — the fixes focus on correctness, not speed.
- **Changing the `@_register` decorator API** — backwards-compatible wrapper fixes only.
