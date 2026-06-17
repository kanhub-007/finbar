# Implementation Guide — Fix IB Handler NameError

---

### Step 1: Add constants to inside_bar.py
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/handlers/inside_bar.py`

Insert three constants before the `_get_ib_bars` function definition (around line 54):

```python
# Bars per initial balance period for common intervals.
_IB_BARS_MAP = {"5min": 12, "15min": 4, "30min": 2, "1h": 1}
_DEFAULT_IB_BARS = 2
_IB_MINUTES_MAP = {"5min": 5, "15min": 15, "30min": 30, "1h": 60}
```

**Before:**
```python
def _get_ib_bars(df: pd.DataFrame) -> int:
    """Determine how many bars make up the initial balance period.
    ...
```

**After:**
```python
# Bars per initial balance period for common intervals.
_IB_BARS_MAP = {"5min": 12, "15min": 4, "30min": 2, "1h": 1}
_DEFAULT_IB_BARS = 2
_IB_MINUTES_MAP = {"5min": 5, "15min": 15, "30min": 30, "1h": 60}


def _get_ib_bars(df: pd.DataFrame) -> int:
    """Determine how many bars make up the initial balance period.
    ...
```

**Verify:** 
```bash
python -c "from finbar_strategy_runtime.indicators.handlers.inside_bar import _get_ib_bars; print('OK')"
```

---

### Step 2: Remove dead constants from trend_breakout.py (optional — Slice 2)
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/handlers/trend_breakout.py`

Remove lines 153–155:
```python
_IB_BARS_MAP = {"5min": 12, "15min": 4, "30min": 2, "1h": 1}
_DEFAULT_IB_BARS = 2
_IB_MINUTES_MAP = {"5min": 5, "15min": 15, "30min": 30, "1h": 60}
```

Also remove the comment block above them (lines 149–152):
```python
# Bars per initial balance period for common intervals.
# 5min: 12 bars = 1 hour. 15min: 4 bars. 30min: 2 bars. 1h: 1 bar.
```

**Verify:**
```bash
grep -n "_IB_BARS_MAP\|_IB_MINUTES_MAP\|_DEFAULT_IB_BARS" \
  packages/strategy-runtime/finbar_strategy_runtime/indicators/handlers/trend_breakout.py
# → No output
```

---

### Step 3: Run existing tests
**Command:**
```bash
cd packages/strategy-runtime && python -m pytest tests/ -x -q -k "ib"
```

**Expected:** All IB-related tests pass.

---

### Step 4: Integration test via MCP
Use finbar MCP `compute_indicators` on intraday data:
```json
["ib_high","ib_low","ib_range","ib_midpoint"]
```

**Verify:**
- No `failed_indicators` for any ib_* metric
- `ib_high` has non-null values on day 2+ bars
- Within each calendar day, ib_high/ib_low/ib_range/ib_midpoint are constant

---

### Step 5: Regression test — daily data still rejects IB
```json
["ib_high"]
# On interval "1d" → ib_high = null (correct: IB is intraday-only)
```

**Common mistake:** Accidentally making IB work on daily data. The `_get_ib_bars` function should still return a small number on daily data (1 or 2 bars), but `_compute_true_ib` groups by date — each day has 1 bar, so `len(group) >= ib_bars` is true but IB is meaningless. This is acceptable; the metric catalog already marks IB as intraday-only.
