# Streaming Enrichment Performance

## User Story
As a strategy developer using MCP tools or Finbot live trading, I want causal
streaming enrichment to complete within seconds for multi-week datasets, so that
backtest iteration is fast and live bars are processed within the candle interval.

## Context
The causal streaming enricher processes each bar through `StreamingIndicatorEngine`.
After the `BatchedWindowedState` optimization (Scenario 1), all windowed metrics
share a single deque buffer and batch compute pass — a ~10× speedup. However,
there are three remaining bottlenecks:

1. **Window oversizing**: `_SESSION_COUNT_WINDOW` is hardcoded at 500 bars for
   all session-count metrics (poc_slope_5, wyckoff_phase). On 30min crypto a
   session is 48 bars; poc_slope_5 needs 5 × 48 = 240. The extra 260 bars are
   pure computation waste.

2. **Session VP recompute**: Even with batched state, every bar still runs the
   full VP batch computation on the entire window. Within a single session, VP
   (POC/VAH/VAL) changes incrementally — new bars only shift the volume-weighted
   distribution slightly. We can maintain an incremental distribution that
   updates O(log bins) per bar and only materialize POC/VAH/VAL values.

3. **Sequential timeframes**: MTF strategies process primary (30min) and
   informative (1h) engines sequentially. These are completely independent —
   no data flows between them until the merge step. They can run in parallel.

## Non-Goals
- Changing VP computation semantics (POC/VAH/VAL values must remain identical)
- Changing the merge/batch handler output format
- Parallelism across bars within a single engine (order-dependent)
- GPU acceleration or compiled extensions (numba/Cython)
