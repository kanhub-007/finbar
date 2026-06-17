# Architecture Decisions — Streaming Indicator Calculator

## ADR-1: Streaming engine alongside the batch calculator (not a replacement)

**Context:** `PandasTaIndicatorCalculator.calculate()` recomputes all
indicators over the full frame each call. Downstream live consumers read
only the latest row, so the work is `O(n)` per candle in `n = warmup
length` rather than in the number of new bars (one). Options considered:

- **(a) Frame memoization** — cache the enriched frame keyed by an input
  signature (last timestamp + length). Rejected for the live path: Finbot
  calls `calculate()` exactly once per candle, so the cache never hits.
  Useful only if a future caller invokes `calculate()` repeatedly on an
  unchanged frame.
- **(b) `calculate_last()` returning only the latest row** — removes the
  `df.copy()` + column-assignment allocation but still recomputes the
  full `O(n)` indicator arrays. Modest gain; adopted as a *fallback*
  inside the streaming engine for windowed indicators, and exposed as a
  backward-compatible entry point (Scenario 9).
- **(c) Streaming / incremental engine** — per-bar online updates with
  bounded state. Reduces per-candle cost for streaming indicators from
  `O(n)` to `O(1)`; for windowed indicators from `O(n)` to `O(window)`.

**Decision:** Implement **(c)** as a new `StreamingIndicatorCalculator`
interface + `StreamingIndicatorEngine`, keeping the batch
`IndicatorCalculator.calculate()` path unchanged. Windowed indicators
fall back to a bounded-window recompute (option b applied to just the
window) in the first slice; true sliding-window VP is deferred to a
later slice.

**Consequences:**
- Two implementations of "compute these indicators" exist — the
  **Strategy** pattern, chosen because the two consumers have opposite
  data shapes (a full frame vs one bar at a time). A single interface
  with an optional streaming method would violate interface segregation.
- Parity is the central risk: streaming numeric seeds (EMA/RSI/ATR
  initialisation) must match `pandas_ta` exactly. The randomised parity
  property test (Scenario 7) is the guard and must run in CI for every
  indicator set.
- Backtest, replay, and validation are unaffected (they keep using the
  batch path), so historical results do not shift.
- Per-bar memory is bounded and independent of `n` for streaming
  indicators, enabling high-cadence and multi-ticker runtimes.

## ADR-2: Parity is the correctness contract, verified by a property test

**Context:** A streaming implementation can produce values that are
"close" to the batch implementation but drift after many bars
(accumulating smoothing error) — silently wrong signals in live trading.

**Decision:** The defining correctness property is: *for the same input
sequence, streaming latest-row value == batch last-row value, within
`atol=1e-12, rtol=1e-9`* (windowed VP uses a looser `rtol=1e-7`,
documented in the scenario). A randomised, parametrised parity test
(Scenario 7) runs in CI over every supported indicator set and many
random sequences (lengths 50–500).

**Consequences:**
- Every new streaming indicator must be added to
  `SUPPORTED_STREAMING_SETS` / `ALL_PARITY_SETS` (see 03-domain.md) or the
  parity test cannot prove it. Windowed-default indicators get the loose
  tolerance (`rtol=1e-7`); hand-written STREAMING indicators get the tight
  (`rtol=1e-9`). Adding a windowed-default indicator to a parity set does
  NOT require a hand-written state class — it proves the fallback works.
- Tolerance changes require an ADR entry (they are a correctness knob,
  not a tuning parameter).

## ADR-3: Fail closed only on genuinely unknown names (windowed-default narrows the scope)

**Context:** A strategy may request an indicator for which no streaming
state exists. The original draft of this spec had every non-hand-written
indicator raise at construction — but verification (2026-06-16) showed
that would crash construction for **183 of 229** registered handlers
(every price-action/SMC/VSA/microstructure/proxy/AMT indicator), making
the spec unadoptable.

**Decision:** Two-tier policy:
1. **`UNKNOWN` (fail-closed)** — a name with **no registered handler**
   and no matching dynamic/VP pattern raises
   `UnsupportedStreamingIndicatorError` at construction. This catches
   typos and genuinely unregistered metrics. No silent NaN.
2. **`WINDOWED` (windowed-default)** — a name with a registered handler
   but no hand-written streaming state class falls back to
   `WindowedIndicatorState(maxlen=max(min_lookback, MIN_BARS))`. It is
   computable (correct, `O(window)`) rather than fail-closed.

**Consequences:**
- ✅ Every catalogued metric is computable under streaming. Count of
  indicators that fail-closed after this rule: **0** (assuming every
  catalogued name is registered, which `_validate_consistency` enforces).
- ✅ Adding a new indicator to the package requires no streaming-spec
  change to be *computable* — it auto-falls-back to windowed. It needs a
  hand-written state class only to be *fast* (O(1) vs O(window)).
- ⚠️ Windowed-default indicators are correct but pay `O(window)` per bar.
  For a live strategy with many such indicators this can exceed the 1ms
  budget (Scenario 10). Mitigation: the budget test surfaces which
  indicators are hot; those get hand-written state classes in later slices.
- 📝 The parity suite (Scenario 7 + 8b) includes windowed-default
  representatives per family, so correctness of the fallback is verified,
  not assumed.

## ADR-4: Shared sub-state per indicator family (MACD)

**Context:** MACD's three outputs (`macd`, `macd_signal`, `macd_hist`)
derive from one EMA(12), EMA(26), and signal EMA(9). Computing them
independently would triple the EMA work and risk divergence.

**Decision:** One `MacdState` owns the three EMAs and serves all three
outputs; the engine instantiates it once regardless of which subset of
the three is requested. This mirrors the batch calculator's per-call
`cache` for MACD/BB.

**Consequences:** Requesting only `macd_signal` yields the identical
value as requesting all three (Scenario 3 single-source-of-truth
assertion). Extends naturally to BB (one rolling mean+variance state for
upper/middle/lower) and to any future multi-output indicator.
