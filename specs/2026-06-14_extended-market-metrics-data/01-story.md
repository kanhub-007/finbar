# Extended Market Metrics and Data Requirements

## User Story
As a Finbar strategy author, I want Finbar to expose a broader catalog of market metrics with explicit data requirements, so that strategies can use advanced trading theories only when the available data is sufficient and receive clear diagnostics when it is not.

## Context
The trading theory documents describe metrics beyond current Finbar support: spread estimators, liquidity/impact proxies, OFI/VPIN/PIN, jump/tail-risk, intraday seasonality, resiliency, information share, Fibonacci, SMC, VSA, supply/demand zones, behavioral/sentiment inputs, and true order-flow methods.

Finbar currently supports many OHLCV-based indicators and AMT/profile tools, but several gaps require different data classes. Daily or intraday OHLCV can support many proxies, but cannot support true bid/ask spread, Level 2 depth, DOM, tape, footprint, Lee-Ready classification, absorption/iceberg detection, actual PIN, or information-share models without quotes/trades/order-book data. This feature adds a metric capability/data-requirement registry and staged implementation of feasible metrics while explicitly flagging unsupported data requirements.

**Package placement note:** After the strategy runtime package extraction (`2026-06-14_extract-strategy-runtime-package`) is complete, all new metric calculators and the metric catalog should be added to `finbar_strategy_runtime/domain/services/` (pure math) and `finbar_strategy_runtime/indicators/` (pandas-backed calculators), NOT `finbar/core/domain/services/`. This ensures Finbot can also use the same metrics for live evaluation. The file paths in this spec's implementation guide use `finbar/core/...` as the current location; adjust to `finbar_strategy_runtime/...` once extraction is done.

## Non-Goals
- Pretending OHLCV is enough for tick/quote/order-book-only metrics.
- Buying or integrating paid data feeds in the first slice.
- Implementing live HFT/order-book execution.
- Replacing existing Finbar OHLCV indicator workflows.
- Implementing every documented metric in one release.
