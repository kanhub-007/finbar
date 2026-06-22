# Implementation Guide — Streaming Performance

## Slice 1 — Tighten Window Sizes

### Step 1: Per-metric session-count windows
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/streaming_indicator_engine.py`

Replace the flat `_SESSION_COUNT_WINDOW = 500` with a function that multiplies
the session lookback by bars-per-session. Keep the `_SESSION_COUNT_NAMES`
frozenset but add a parser for poc_slope_N.

```python
_BARS_PER_SESSION = 48  # crypto default at 30min

def _session_count_window(name: str) -> int | None:
    if name == "wyckoff_phase":
        return 5 * _BARS_PER_SESSION  # 240
    if name == "value_area_migration":
        return 5 * _BARS_PER_SESSION
    if name.startswith("poc_slope_"):
        try:
            n = int(name[len("poc_slope_"):])
            return (n + 1) * _BARS_PER_SESSION
        except ValueError:
            pass
    return None
```

**Verify:** `python -m pytest tests/contract/test_streaming_engine.py -q`
**Common mistake:** Forgetting that poc_slope needs N+1 sessions (N slopes).

### Step 2: Add test for window sizing
**File:** `packages/strategy-runtime/tests/contract/test_streaming_engine.py`

Add parametrized test verifying window sizes for all session-count metrics.

---

## Slice 2 — Incremental Session VP

### Step 3: Create IncrementalSessionVpState
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/incremental_session_vp_state.py`

Maintain a dict[price_level, volume] within a session. On each bar:
1. If session changed, reset distribution
2. Add bar's volume to price bins: high, low (boundary), close covers typical
3. When a VP value is requested, materialize POC/VAH/VAL from distribution
4. VAH/VAL = prices at 70% of total volume around POC

```python
class IncrementalSessionVpState:
    def __init__(self):
        self._bins: dict[float, float] = {}  # price → cum_vol
        self._total_vol = 0.0
        self._session_date: str | None = None

    def update(self, bar: dict) -> SessionVpLevels:
        # Check session boundary
        # Add bar volume at (high+low+close)/3 rounded to tick
        # Compute POC (max vol bin)
        # Compute VAH/VAL (70% volume around POC)
        return SessionVpLevels(poc, vah, val)
```

**Verify:** `python -m pytest tests/contract/test_incremental_session_vp.py -q`

### Step 4: Integrate into streaming engine
**File:** Same as Step 1

In `_build_state()`, route `vp_poc`, `vp_vah`, `vp_val` to the new state.
The incremental state returns a `SessionVpLevels` namedtuple; the engine
reads `.poc` / `.vah` / `.val` from it for each requested metric.

### Step 5: Adapt derived AMT metrics
Derived metrics (`near_val`, `above_value`, etc.) already read from the
DataFrame columns `vp_poc`, `vp_vah`, `vp_val`. With the incremental state,
these columns are materialized by the VP handler once per bar. The
`BatchedWindowedState` still handles them in one batch call — the incremental
VP state just feeds the values in faster.

---

## Slice 3 — Parallel Timeframe Enrichment

### Step 6: Parallelize causal_enrich_bars
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/causal_multi_timeframe_streaming_enricher.py`

Use `concurrent.futures.ThreadPoolExecutor` to run informative enrichment in
parallel with primary enrichment. Since engines are independent until merge,
no shared state needs locking.

```python
with ThreadPoolExecutor(max_workers=len(info_bars) + 1) as executor:
    primary_future = executor.submit(_enrich_primary, ...)
    info_futures = {alias: executor.submit(_enrich_informative, ...) for ...}
    primary_rows = primary_future.result()
    info_rows = {a: f.result() for a, f in info_futures.items()}
    return _merge(primary_rows, info_rows)
```

**Verify:** `python -m pytest tests/contract/test_causal_mtf_enricher_perf.py -q`
**Common mistake:** Primary must still respect informative bar visibility (no future info bars).
