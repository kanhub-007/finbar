# Extract Strategy Runtime Package

## User Story
As a Finbar maintainer, I want the strategy definition/runtime code extracted into a dedicated installable package, so that Finbar can author/backtest strategies and Finbot can execute the same strategies live without copying runtime code.

## Context
Finbar currently owns the canonical strategy schema, parser, indicator catalog, condition evaluator, risk calculator, and rule-based strategy runtime. Finbot copied much of this subset to stay standalone, but copied code can drift and break live/backtest parity.

The shared runtime must be suitable for two intents: Finbar uses it for strategy creation, validation, enrichment, backtesting, optimization, and explanation; Finbot uses it for live candle enrichment, deterministic strategy evaluation, and safe signal generation. The package must stop at the signal/runtime boundary. Data fetching, REST/MCP, persistence, backtesting engines, optimization jobs, and live order execution remain in their owning applications.

This spec covers migration steps 1-3: create the package boundary, add contract/parity tests, and refactor Finbar to consume the package.

## Non-Goals
- Publishing Finbar's full service as a Finbot dependency.
- Moving Finbar REST/MCP tools, SQL repositories, fetchers, job managers, backtest result stores, or optimization engines into the runtime package.
- Adding new strategy indicators or metrics in this extraction slice.
- Changing strategy schema semantics unless required to remove app-specific coupling.
- Making Finbot import the package; that is covered by the Finbot import spec.
