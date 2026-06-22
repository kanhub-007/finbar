# Scenarios — Streaming Enrichment Performance

All tests follow Classical/Detroit + black-box principles. Assert on outcomes
(per-bar values, enrichment parity), not internal interactions.

## Slice 1 — Tighten Window Sizes

### Scenario 1: Session-count metrics use per-metric minimum windows
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given session-count metrics (poc_slope_5, wyckoff_phase, value_area_migration)
  When the streaming engine resolves their window size
  Then the window is exactly the session lookback × bars-per-session, not 500
  And non-session metrics are unaffected

**Input table:**
| Metric | Current window | Bars/session (30min crypto) | Expected window |
|--------|---------------|------------|-----------------|
| poc_slope_5 | 500 | 48 | 5 × 48 = 240 |
| poc_slope_20 | 500 | 48 | 20 × 48 = 960 |
| wyckoff_phase | 500 | 48 | ~240 (5 sessions) |
| vp_poc | catalog.min_lookback | — | unchanged |

**Expected output:**
| Assertion | How to verify |
|---|---|
| `_resolve_window("poc_slope_5")` returns 240 for 30min | Direct call |
| `_resolve_window("poc_slope_5")` returns 120 for 1h | Direct call (1h = 24 bars/session) |
| `_resolve_window("vp_poc")` unchanged | Direct call |
| Streaming enrichment produces identical values | Causal parity sweep passes |

**Verify:**
```python
engine_30m = StreamingIndicatorEngine(indicators=["poc_slope_5"])
# window should be ~240, not 500
assert engine_30m._resolve_window("poc_slope_5") <= 300

engine_1h = StreamingIndicatorEngine(indicators=["poc_slope_5"])
assert engine_1h._resolve_window("poc_slope_5") <= 150
```

**Also test:**
- Interval not provided → conservatively assume 48 bars/session (crypto default)
- Window never goes below MIN_BARS (10)
- Existing catalog-based windows (via min_lookback) are unchanged

## Slice 2 — Incremental Session VP

### Scenario 2: Session VP updates without full-window recompute
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given session VP metrics (vp_poc, vp_vah, vp_val) streaming through a session
  When a new bar arrives within the same session
  Then the VP value updates via incremental bin updates, not full-window recompute
  And the value matches the batch-prefix oracle exactly

**Input table:**
| Field | Type | Example | Constraints |
|---|---|---|---|
| bars | list[dict] | 96 bars (2 sessions of 30min crypto) | Sorted, timestamped |
| metric | str | "vp_poc" | Any session VP metric |

**Expected output:**
| Assertion | How to verify |
|---|---|
| Streaming value = prefix oracle at every row | Causal prefix comparison |
| No full-window DataFrame conversion within a session | Performance measurement |
| Session boundary triggers distribution reset | Inspect state reset |

**Verify:**
```python
state = IncrementalSessionVpState(name="vp_poc")
for bar in bars:
    got = state.update(bar)
    expected = batch_calc.calculate(prefix_frame, ["vp_poc"]).iloc[-1]["vp_poc"]
    assert_equivalent(got, expected)
```

**Also test:**
- Session boundary resets the distribution
- First bar of new session produces correct VP for one bar
- Multi-session dataset matches batch oracle at every row

### Scenario 3: Derived AMT metrics still work with incremental VP
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given derived AMT metrics (near_val, above_value, rejection_from_edge, etc.)
  When the underlying session VP is incrementally updated
  Then the derived metrics still match the batch-prefix oracle
  And they use the same incremental VP state (no duplication)

**Verify:**
```python
for metric in AMT_DERIVED:
    assert_metric_matches_prefix_oracle(metric, bars, sample_indices=[48, 96, 144])
```

**Also test:**
- poc_slope_5 still works with incremental VP as input
- value_area_width_pct = (VAH - VAL) / POC still correct
- profile_shape, wyckoff_phase still match oracle

## Slice 3 — Parallel Timeframe Enrichment

### Scenario 4: Primary and informative engines run in parallel
**Priority:** Should
**Slice:** 3

**Gherkin:**
  Given an MTF strategy with primary (30min) and informative (1h) engines
  When the causal enricher feeds bars through both engines
  Then the engines run in parallel threads
  And enrichment latency is reduced compared to sequential
  And output values are identical to sequential execution

**Verify:**
```python
sequential = causal_enrich_bars(primary, info, ..., parallel=False)
parallel = causal_enrich_bars(primary, info, ..., parallel=True)
assert_frames_equal(sequential, parallel)
assert parallel_elapsed < sequential_elapsed * 0.8
```

**Also test:**
- Single-timeframe strategies (no informative) are unaffected
- Thread safety — no shared mutable state between engines
- Informative bar feeding timeline is respected (no future bars leak)
