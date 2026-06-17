# Scenarios — Streaming Indicator Calculator

Scenarios ordered by MoSCoW. Slice 1 = all Musts (parity + streaming
core + reset + warmup + randomised parity + windowed-default adoptability).
Slice 2 = Shoulds (VP windowed fallback, batch-last fallback, performance
budget). Slice 3 = Coulds.

> **Scenario 8b (windowed-default) is a Must in Slice 1** because without
> it ~183 of 229 indicators crash engine construction. Scenario 8
> (VP-prefix windowed) is a Should in Slice 2 — it's an optimisation for a
> specific family, not an adoptability gate.

All `Verify` blocks use **Classical (Detroit) school + black-box** tests:
real indicator engines, no mocking of handlers; assertions on *outcome*
(returned latest values), never on which internal methods were called.

The defining correctness oracle is **parity with the batch calculator**:
for the same sequence of bars, the streaming engine's latest-row value
for an indicator must equal the batch calculator's last-row value for
that indicator, within float tolerance `atol=1e-12, rtol=1e-9`.

---

### Scenario 1: Streaming equals batch for a simple rolling indicator (SMA)
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a fixed seed and 50 deterministic OHLCV bars
  When  the streaming engine ingests the bars one at a time
  Then  its latest-row `sma_20` equals the batch `calculate()` last-row
        `sma_20` within float tolerance

**Input table:**
| Field        | Type   | Example / Constraint                       |
|--------------|--------|--------------------------------------------|
| bars         | list   | 50 OHLCV dicts, deterministic (fixed seed) |
| indicators   | list   | `["sma_20"]`                               |
| tolerance    | tuple  | `atol=1e-12, rtol=1e-9`                    |

**Expected output / state change:**
| Assertion                                                  | How to verify                                  |
|------------------------------------------------------------|------------------------------------------------|
| `streaming.latest()["sma_20"] == batch_last["sma_20"]`     | `math.isclose(..., rel_tol=1e-9, abs_tol=1e-12)` |

**Verify (Classical school, black-box):**
```python
bars = make_deterministic_bars(50, seed=1)
batch_calc = PandasTaIndicatorCalculator()
batch_last = batch_calc.calculate(bars_to_frame(bars), ["sma_20"]).iloc[-1].to_dict()

engine = IncrementalIndicatorEngine(indicators=["sma_20"])
for b in bars:
    engine.update(b)
streaming_last = engine.latest()

assert math.isclose(streaming_last["sma_20"], batch_last["sma_20"],
                    rel_tol=1e-9, abs_tol=1e-12)
```

**Also test:**
- `sma_200` over 250 bars (parity at the minimum-usable boundary).
- Dynamic period: `sma_37` over 50 bars.
- SMA returns `NaN` (or absent) before `period` bars, matching batch.

---

### Scenario 2: Streaming equals batch for recursive indicators (EMA / RSI / ATR)
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given 100 deterministic OHLCV bars
  When  the streaming engine ingests them one at a time
  Then  `ema_26`, `rsi_14`, and `atr` each equal the batch last-row
        value within float tolerance

**Input table:**
| Field       | Type | Example / Constraint   |
|-------------|------|------------------------|
| bars        | list | 100 OHLCV dicts        |
| indicators  | list | `["ema_26","rsi_14","atr"]` |

**Expected output / state change:**
| Assertion                                                  | How to verify      |
|------------------------------------------------------------|--------------------|
| each streaming value ≈ batch last-row value                | `math.isclose(...)`|

**Verify (Classical school, black-box):**
```python
indicators = ["ema_26", "rsi_14", "atr"]
bars = make_deterministic_bars(100, seed=7)
batch_last = (PandasTaIndicatorCalculator()
              .calculate(bars_to_frame(bars), indicators)
              .iloc[-1].to_dict())

engine = IncrementalIndicatorEngine(indicators=indicators)
for b in bars:
    engine.update(b)
streaming_last = engine.latest()

for name in indicators:
    assert math.isclose(streaming_last[name], batch_last[name],
                        rel_tol=1e-9, abs_tol=1e-12), name
```

**Also test:**
- Numerical stability over a long stream (e.g. 2000 bars) — RSI must not
  drift beyond tolerance vs batch at the final bar (Wilder smoothing
  accumulates; confirm our seed/init matches `pandas_ta`).
- ATR over bars with zero range (high == low) does not go NaN after warmup.

---

### Scenario 3: Multi-output indicator shares sub-state (MACD)
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given 100 deterministic OHLCV bars
  When  the streaming engine computes `macd`, `macd_signal`, `macd_hist`
        from a single internal EMA(12)/EMA(26)/EMA(9) state
  Then  all three outputs equal the batch last-row values within tolerance

**Input table:**
| Field      | Type | Example / Constraint                          |
|------------|------|-----------------------------------------------|
| bars       | list | 100 OHLCV dicts                               |
| indicators | list | `["macd","macd_signal","macd_hist"]`          |

**Expected output / state change:**
| Assertion                                          | How to verify      |
|----------------------------------------------------|--------------------|
| each of the 3 ≈ batch last-row                     | `math.isclose(...)`|
| EMA(12)/EMA(26)/signal EMA computed exactly once per bar | inspect that requesting only `macd_signal` produces an identical value (single source of truth) |

**Verify (Classical school, black-box):**
```python
indicators = ["macd", "macd_signal", "macd_hist"]
bars = make_deterministic_bars(100, seed=3)
batch_last = (PandasTaIndicatorCalculator()
              .calculate(bars_to_frame(bars), indicators)
              .iloc[-1].to_dict())

engine = IncrementalIndicatorEngine(indicators=indicators)
for b in bars:
    engine.update(b)
got = engine.latest()
for name in indicators:
    assert math.isclose(got[name], batch_last[name], rel_tol=1e-9, abs_tol=1e-12)

# single source of truth: requesting only the signal still gives the same value
engine2 = IncrementalIndicatorEngine(indicators=["macd_signal"])
for b in bars:
    engine2.update(b)
assert math.isclose(engine2.latest()["macd_signal"], got["macd_signal"],
                    rel_tol=1e-9, abs_tol=1e-12)
```

---

### Scenario 4: Streaming consumes one bar per update and returns latest row only
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a streaming engine configured with a set of streaming indicators
  When  `update(bar)` is called with successive bars
  Then  each call returns / makes available the latest-row dict of scalars
        and the engine allocates no new full-length Series

**Input table:**
| Field       | Type | Example / Constraint                                  |
|-------------|------|-------------------------------------------------------|
| indicators  | list | `["sma_20","ema_26","rsi_14","atr","macd","ibs","vwap"]` |

**Expected output / state change:**
| Assertion                                              | How to verify                          |
|--------------------------------------------------------|----------------------------------------|
| `engine.update(bar)` returns the latest-row dict       | inspect return value / `latest()`      |
| Memory growth is bounded (no `n`-length arrays stored) | `tracemalloc` before/after N updates   |

**Verify (Classical school, black-box):**
```python
engine = IncrementalIndicatorEngine(indicators=[...])
latest = None
for b in make_deterministic_bars(60, seed=2):
    latest = engine.update(b)
assert latest is not None
assert "rsi_14" in latest
# bounded memory: feeding 10_000 more bars must not grow allocations with n
import tracemalloc
tracemalloc.start()
before = tracemalloc.get_traced_memory()[0]
for b in make_deterministic_bars(10_000, seed=99):
    engine.update(b)
after = tracemalloc.get_traced_memory()[0]
assert (after - before) < 1_000_000  # < ~1 MB growth over 10k bars
```

**Also test:**
- `latest()` without any prior `update()` returns `{}` or raises a clear
  error (define in domain model — recommend `{}`).

---

### Scenario 5: Warmup semantics match batch `MIN_BARS`
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a batch calculator that skips indicators below `MIN_BARS = 10`
  When  the streaming engine has ingested fewer than `MIN_BARS` bars
  Then  it reports not-ready and `latest()` contains no indicator values
  And   once `MIN_BARS` bars are ingested it becomes ready

**Input table:**
| Field      | Type | Example / Constraint            |
|------------|------|---------------------------------|
| MIN_BARS   | int  | `10` (from batch calculator)    |

**Expected output / state change:**
| Assertion                              | How to verify                |
|----------------------------------------|------------------------------|
| `engine.is_ready()` is False < 10 bars | `assert not engine.is_ready()`|
| `engine.is_ready()` is True ≥ 10 bars  | `assert engine.is_ready()`    |

**Verify (Classical school, black-box):**
```python
engine = IncrementalIndicatorEngine(indicators=["sma_20"])
bars = make_deterministic_bars(10, seed=5)
for b in bars[:-1]:
    engine.update(b)
assert not engine.is_ready()
engine.update(bars[-1])
assert engine.is_ready()
```

---

### Scenario 6: Reset clears per-indicator state
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a streaming engine that has ingested bars
  When  `reset()` is called
  Then  a subsequent re-ingestion of the same bars reproduces identical
        latest values, and internal crossover/EMA state is empty

**Verify (Classical school, black-box):**
```python
bars = make_deterministic_bars(80, seed=4)
engine = IncrementalIndicatorEngine(indicators=["ema_26", "rsi_14"])
for b in bars:
    engine.update(b)
first = dict(engine.latest())

engine.reset()
assert not engine.is_ready()
for b in bars:
    engine.update(b)
second = engine.latest()
for name in ("ema_26", "rsi_14"):
    assert math.isclose(second[name], first[name], rel_tol=1e-12, abs_tol=1e-15)
```

---

### Scenario 7: Randomised parity over many indicator sets and sequences
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a parametrised list of indicator sets and many random OHLCV sequences
  When  batch and streaming are fed the same bars
  Then  every supported indicator's last-row value is within tolerance

**Input table:**
| Field          | Type     | Example / Constraint                                    |
|----------------|----------|---------------------------------------------------------|
| indicator_sets | list     | `ALL_PARITY_SETS` — streaming + dynamic + VP + windowed-default reps (see 03-domain.md) |
| sequences      | iterator | ≥ 20 random sequences, lengths ∈ [50, 500], fixed seeds |
| tolerance      | tuple    | tight `atol=1e-12, rtol=1e-9` for STREAMING/dynamic; loose `atol=1e-9, rtol=1e-7` for WINDOWED/windowed-default |

**Verify (Classical school, black-box — the parity property test):**
```python
# ALL_PARITY_SETS is defined in 03-domain.md. Each set carries its own
# tolerance (tight for hand-written state, loose for windowed fallback).
@pytest.mark.parametrize("indicator_set, tol", ALL_PARITY_SETS_WITH_TOL)
def test_streaming_matches_batch(indicator_set, tol):
    for seed in range(20):
        bars = make_random_bars(length=rng.integers(50, 500), seed=seed)
        batch_last = (PandasTaIndicatorCalculator()
                      .calculate(bars_to_frame(bars), indicator_set)
                      .iloc[-1].to_dict())
        engine = IncrementalIndicatorEngine(indicators=indicator_set)
        for b in bars:
            engine.update(b)
        got = engine.latest()
        for name in indicator_set:
            # Skip NaN↔NaN (warmup window not complete is acceptable).
            if got[name] == got[name] and batch_last[name] == batch_last[name]:
                assert math.isclose(got[name], batch_last[name],
                                    rel_tol=tol.rtol, abs_tol=tol.atol), (seed, name)
```

**Also test:**
- A sequence shorter than the longest period (parity holds for whatever
  batch returns, including `NaN`).
- Degenerate bars: flat (open==high==low==close), zero volume, gaps.

---

### Scenario 8: Windowed indicator falls back to bounded-window recompute
**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given a windowed indicator (e.g. `rvp_poc_48` rolling-window VP)
  When  the streaming engine updates bar-by-bar while retaining the last
        `window` bars in a bounded ring buffer
  Then  its latest value equals the batch last-row value within tolerance
  And   the engine stores at most `window` bars of history (not `n`)

**Input table:**
| Field      | Type | Example / Constraint                |
|------------|------|-------------------------------------|
| indicator  | str  | `"rvp_poc_48"`                      |
| window     | int  | 48 (parsed from the indicator name) |

**Expected output / state change:**
| Assertion                                              | How to verify                          |
|--------------------------------------------------------|----------------------------------------|
| latest ≈ batch last-row                                | `math.isclose(...)`                    |
| retained history ≤ window bars                         | `tracemalloc` / internal bound         |

**Verify (Classical school, black-box):**
```python
bars = make_deterministic_bars(200, seed=8)
batch_last = (PandasTaIndicatorCalculator()
              .calculate(bars_to_frame(bars), ["rvp_poc_48"])
              .iloc[-1].to_dict())
engine = IncrementalIndicatorEngine(indicators=["rvp_poc_48"])
for b in bars:
    engine.update(b)
assert math.isclose(engine.latest()["rvp_poc_48"],
                    batch_last["rvp_poc_48"], rel_tol=1e-7, abs_tol=1e-9)
```

**Note:** volume-profile parity tolerance may need to be looser
(`rtol=1e-7`) because the windowed recompute truncates/extends the
session bucket grid. Pin the exact tolerance from the batch reference in
the implementation; document it in `03-domain.md`.

---

### Scenario 8b: Any registered handler falls back to windowed-default
**Priority:** Must
**Slice:** 1

> This is the adoptability guard. Without it, ~183 of 229 indicators
> (every handler without a hand-written state class) would raise
> `UnsupportedStreamingIndicatorError` at construction and **crash any
> live strategy that reads one of them** (e.g. `bearish_fvg`,
> `corwin_schultz_spread`, any `proxy_*`). The windowed-default rule
> makes them all computable (correct, `O(window)`).

**Gherkin:**
  Given an indicator with a registered handler but no hand-written
        streaming state class (e.g. `bearish_fvg`, `proxy_vwap`,
        `corwin_schultz_spread`)
  When  the streaming engine is constructed with it
  Then  construction succeeds (no `UnsupportedStreamingIndicatorError`)
  And   after warmup, `update()` returns a value equal to the batch
        last-row value within loose tolerance
  And   retained history is bounded by `max(min_lookback, MIN_BARS)`

**Input table:**
| Field      | Type | Example / Constraint                              |
|------------|------|---------------------------------------------------|
| indicator  | str  | one of `SUPPORTED_WINDOWED_DEFAULT_SETS` members  |
| window     | int  | `max(MarketMetricDefinition.min_lookback, 10)`    |

**Expected output / state change:**
| Assertion                                              | How to verify                          |
|--------------------------------------------------------|----------------------------------------|
| engine construction does not raise                     | no exception                           |
| latest ≈ batch last-row within loose tolerance         | `math.isclose(..., rtol=1e-7, atol=1e-9)` |
| retained history ≤ window bars                         | internal bound / tracemalloc           |

**Verify (Classical school, black-box):**
```python
@pytest.mark.parametrize("indicator", [
    "bearish_fvg", "demand_zone_score", "corwin_schultz_spread",
    "awesome_oscillator", "proxy_vwap", "poc_rejection", "hurst_exponent",
])
def test_windowed_default_matches_batch(indicator):
    bars = make_deterministic_bars(250, seed=8)  # > hurst min_lookback=100
    batch_last = (PandasTaIndicatorCalculator()
                  .calculate(bars_to_frame(bars), [indicator])
                  .iloc[-1].to_dict())
    engine = IncrementalIndicatorEngine(indicators=[indicator])  # no raise
    for b in bars:
        engine.update(b)
    got = engine.latest()[indicator]
    # Skip NaN↔NaN (warmup not complete is also acceptable if < min_lookback)
    if got == got and batch_last[indicator] == batch_last[indicator]:
        assert math.isclose(got, batch_last[indicator],
                            rel_tol=1e-7, abs_tol=1e-9), indicator
```

**Also test:**
- A genuinely unknown name (e.g. `"typo_metric"`) DOES raise
  `UnsupportedStreamingIndicatorError` — the only fail-closed path.
- The window respects `min_lookback`: an indicator with
  `min_lookback=100` (e.g. `hurst_exponent`) needs ≥100 bars in the ring
  buffer to reach parity; verify parity holds at `bars >= min_lookback`.

**Tolerance rationale:** windowed-default recomputes over a finite
`deque` slice, so floating-point sums differ from the batch full-frame
sum at ~1e-7. This is acceptable (live signals are thresholded at far
looser precision); hand-written STREAMING indicators use the tight
`1e-9` because they replicate pandas_ta exactly.

---

### Scenario 9: `calculate_last()` fallback returns only the latest row
**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given the batch calculator exposes `calculate_last(df, indicators)`
  When  it is called on a full frame
  Then  it returns a single latest-row dict equal to the last row of
        `calculate()`, without requiring callers to materialise columns

**Verify (Classical school, black-box):**
```python
df = bars_to_frame(make_deterministic_bars(80, seed=6))
calc = PandasTaIndicatorCalculator()
full = calc.calculate(df, ["sma_20", "rsi_14"]).iloc[-1].to_dict()
last = calc.calculate_last(df, ["sma_20", "rsi_14"])
for name in ("sma_20", "rsi_14"):
    assert math.isclose(full[name], last[name], rel_tol=1e-12, abs_tol=1e-15)
```

**Purpose:** a backward-compatible, lower-allocation entry point for
callers that cannot adopt the streaming engine yet, and the
implementation strategy for windowed indicators inside the streaming
engine.

---

### Scenario 10: Per-bar update performance budget
**Priority:** Could
**Slice:** 2

**Gherkin:**
  Given a representative indicator set of ~15 streaming + 2 windowed + 2 windowed-default indicators
  When  the engine processes one bar after warmup
  Then  update latency is sub-millisecond and independent of total bars seen

**Verify (Classical school, black-box — benchmark):**
```python
indicators = REPRESENTATIVE_SET_15  # sma/ema/rsi/atr/adx/macd/bb/... + 2 rvp + 2 windowed-default (e.g. bearish_fvg, proxy_vwap)
engine = IncrementalIndicatorEngine(indicators=indicators)
for b in make_deterministic_bars(300, seed=1):  # warm up
    engine.update(b)

# measure steady-state cost, independent of n
t_n500   = timeit(lambda: engine.update(make_bar()), number=1000)
for b in make_deterministic_bars(9700, seed=2):  # grow history seen by engine
    engine.update(b)
t_n10000 = timeit(lambda: engine.update(make_bar()), number=1000)

assert t_n10000 < t_n500 * 1.5          # cost must NOT grow with n
assert t_n10000 / 1000 < 1e-3           # < 1 ms per bar
```

**Also test:**
- The batch `calculate()` cost **does** grow with `n` (documents the
  motivation): `t_batch(10000) > 5 * t_batch(500)`.
