# Implementation Guide — Streaming Indicator Calculator

Ordered steps. Each step ends with a `Verify` command. Follow Red → Green
→ Refactor per the AGENTS TDD workflow: the scenario's `Verify` block is
the failing test written first.

All tests live under `packages/strategy-runtime/tests/contract/` (parity
contracts belong with the package, not in either app).

---

### Step 1: Add the `StreamingIndicatorCalculator` interface + `LatestBar` VO
**File:** `finbar_strategy_runtime/domain/interfaces/streaming_indicator_calculator.py`
**File:** `finbar_strategy_runtime/domain/entities/latest_bar.py`

Define `LatestBar` value object and the ABC exactly as in `03-domain.md`.
No behaviour yet — this is the contract the tests import.

**Verify:** `python -m pytest tests/contract/test_streaming_indicator_interface.py -q`
(test asserts the ABC cannot be instantiated and `LatestBar` exposes
`values`/`is_ready`/`bars_seen`).
**Common mistake:** adding a concrete implementation in the interface
file — keep it abstract.

---

### Step 2: Build the name→kind classifier (Scenario parity helper)
**File:** `finbar_strategy_runtime/indicators/_streaming_classifier.py`

`classify_indicator(name) -> IndicatorKind` and
`UnsupportedStreamingIndicatorError(ValueError)`. Reuse `_handler_registry`
and `_dynamic_dispatch` resolution (do not duplicate the name table).
Implement the **four tiers** in order (see 03-domain.md "Indicator
classification"):
1. Hand-listed STREAMING (the state-class table) → `STREAMING`.
2. Dynamic-period (`sma_N`/`ema_N`/…) → `STREAMING`.
3. VP-prefix (`rvp_*`/`vp_*Nd`/`cvp_*Nd`) → `WINDOWED` with window from
   the name suffix.
4. **Else if `name in _INDICATOR_HANDLERS` → `WINDOWED` with window =
   `max(UnifiedMetricCatalog.get(name).min_lookback, MIN_BARS)`.** This
   is the windowed-default rule that makes the spec adoptable (covers
   the ~183 handlers with no hand-written state class).
5. Else → `UNKNOWN` (raises at construction).

Also add a `classify_indicator` test that asserts **every registered
handler name** resolves to STREAMING or WINDOWED (never UNKNOWN) — the
adoptability guard. There are 229 handlers; all must be covered.

**Verify:** `pytest tests/contract/test_streaming_classifier.py -q`
(parametrised over all 229 registered handler names + dynamic prefixes +
the UNKNOWN case).

---

### Step 3: Streaming SMA state (Scenario 1 — first Red/Green)
**File:** `finbar_strategy_runtime/indicators/streaming/sma_state.py`

`deque(maxlen=length)` running sum. Seed behaviour must match
`pandas_ta.sma` (NaN until `length` bars, first non-NaN = mean of first
`length` closes).

**Verify:** Scenario 1 (`test_streaming_sma_parity`). Run the randomised
parity loop at `length ∈ {10, 20, 37, 50, 200}`.
**Common mistake:** off-by-one on the first valid index; compare against
`batch.iloc[-1][name]`, not a hand-computed value.

---

### Step 4: Recursive states — EMA, RSI, ATR (Scenario 2)
**Files:** `.../streaming/ema_state.py`, `rsi_state.py`, `atr_state.py`

- **EMA:** seed = SMA of first `length` values (this is how `pandas_ta`
  initialises), then `α = 2/(length+1)`.
- **RSI:** Wilder smoothing; seed avg-gain/avg-loss over first `length`
  bars; `α = 1/length`.
- **ATR:** Wilder TR smoothing, `length=14`.

**Verify:** Scenario 2 + the 2000-bar drift test in its "Also test" list.
**Common mistake:** seeding EMA/RSI with the first value instead of the
SMA-of-first-N — produces parity failure that only surfaces after ~100
bars.

---

### Step 5: MACD shared state (Scenario 3)
**File:** `.../streaming/macd_state.py`

One `MacdState` owns `EmaState(12)`, `EmaState(26)`, `EmaState(9)`. The
engine de-duplicates: requesting `["macd", "macd_signal", "macd_hist"]`
constructs exactly one `MacdState`.

**Verify:** Scenario 3, including the single-source-of-truth assertion
(engine configured with only `["macd_signal"]` yields an identical value).

---

### Step 6: Remaining streaming families (Scenarios 4, 7)
**Files:** `adx_state.py`, `bb_state.py`, `ker_state.py`, `kama_state.py`,
`vwap_state.py`, `ibs_state.py`, `rvol_state.py`

Implement each per the algorithm table in `03-domain.md`.

**Verify:** Scenario 7 randomised parity over `ALL_PARITY_SETS`
(streaming + dynamic + VP + windowed-default reps).
**Common mistake:** ADX uses Wilder smoothing on DM± and TR; mismatching
the smoothing length breaks parity.

---

### Step 7: Engine assembly + warmup + reset (Scenarios 4, 5, 6)
**File:** `finbar_strategy_runtime/indicators/streaming/streaming_indicator_engine.py`

`StreamingIndicatorEngine(indicators)` resolves each name to a state
object via the classifier, tracks `bars_seen`, and enforces `MIN_BARS =
10` readiness matching the batch calculator.

**Verify:** Scenarios 4, 5, 6.

---

### Step 8: Windowed fallback (Scenarios 8 + 8b)
**File:** `.../streaming/windowed_indicator_state.py`

`deque(maxlen=window)` + recompute via the existing batch handler on the
window slice. Used for **both** cases:
- VP-prefix indicators (Scenario 8): window parsed from the name suffix
  (reuse `_dynamic_dispatch._is_rolling_vp` logic).
- **Windowed-default indicators (Scenario 8b):** window =
  `max(UnifiedMetricCatalog.get(name).min_lookback, MIN_BARS)`. Same
  `WindowedIndicatorState` class, just a different window source. The
  recompute calls the registered batch handler on the `deque` slice
  (convert to a DataFrame, call `handler(df, name, cache)`, read
  `.iloc[-1][name]`).

This single class covers all ~183 windowed-default indicators plus the
24 VP-prefix ones — no per-indicator code needed.

**Verify:** Scenario 8. **Pin** the VP `rtol` from the fixture and write
it into `02-scenarios.md`.

---

### Step 9: Batch `calculate_last()` fallback (Scenario 9)
**File:** edit `finbar_strategy_runtime/indicators/pandas_ta_indicator_calculator.py`

Add `calculate_last(df, indicators) -> dict` that calls `calculate` and
returns `.iloc[-1].to_dict()`. Optional optimisation (skip column
assignment) deferred — parity first.

**Verify:** Scenario 9.

---

### Step 10: Performance benchmark (Scenario 10)
**File:** `tests/contract/test_streaming_perf_budget.py`

Benchmark steady-state `update()` vs `calculate()` at n=500 and n=10000.
Assert update cost is independent of `n` and < 1 ms/bar; assert batch
cost grows with `n` (documents motivation).

**Verify:** `pytest tests/contract/test_streaming_perf_budget.py -q`.
**Common mistake:** benchmarking with the JIT cold — warm up the engine
for ≥ 300 bars before timing.

---

### Step 11: Register public API + docs
**File:** `finbar_strategy_runtime/__init__.py` — export
`StreamingIndicatorCalculator`, `StreamingIndicatorEngine`.
**File:** update `packages/strategy-runtime/README.md` and the indicator
section of the root README.

**Verify:** `python -c "from finbar_strategy_runtime import StreamingIndicatorEngine"`
and `ruff check . && black --check .`.
