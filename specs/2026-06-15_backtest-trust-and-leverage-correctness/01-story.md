# Backtest Trust and Leverage Correctness

## User Story
As a Finbar user running strategy backtests, I want strategy parsing, indicator preparation, warmup handling, risk prices, and leveraged execution to match documented trading semantics, so that I can trust reported backtest results before using them for live or leveraged trading decisions.

## Context
Finbar already has strong coverage for core bar-by-bar backtesting: next-open entries, gap-aware exits, long/short PnL, costs, data validation, and runtime strategy evaluation. A logic review found several trust-critical gaps around multi-timeframe indicator job intervals, warmup/crossover state, leveraged liquidation assumptions, risk price basis when entries fill at the next open, and simplified borrow/funding assumptions.

This feature hardens those behaviours with explicit contracts, tests, diagnostics, and targeted implementation changes. The goal is not to model every exchange exactly, but to make the backtest engine internally consistent, configurable where assumptions vary, and honest in its trust diagnostics.

## Non-Goals
Things explicitly NOT being built in this iteration:
- Exchange-specific liquidation models for every venue.
- Live order execution or Finbot exchange integration.
- New indicators or strategy schema changes unrelated to backtest trust.
- Tick-level intrabar path reconstruction.
- Portfolio-level cross-margin across multiple simultaneous positions.
