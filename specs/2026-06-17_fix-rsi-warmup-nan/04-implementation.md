# Implementation Guide — RSI Warmup NaN Fix

---

### Step 1: Add warmup masking to _safe_ta
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/_handler_registry.py`

In the `_safe_ta` function, after the `if result is None:` block, add warmup masking:

```python
def _safe_ta(func: Callable, *args, **kwargs) -> pd.Series | None:
    """Call a pandas_ta function and return None-safe result.

    pandas_ta returns None when there are fewer bars than the requested
    period length. This helper converts None to a NaN-filled Series.
    Also masks the first N bars to NaN (warmup) when length= is provided,
    guarding against pandas_ta functions that return partial results.
    """
    try:
        result = func(*args, **kwargs)
    except Exception:
        result = None
    if result is None:
        series = args[0] if args else kwargs.get("close")
        if series is not None and isinstance(series, pd.Series):
            return pd.Series(float("nan"), index=series.index, dtype="float64")
        return None
    
    # Mask warmup bars: first N bars → NaN where N = lookback period.
    # Some pandas_ta functions (e.g. ta.rsi) return partial Series instead
    # of None when there are fewer than `length` bars. This guard ensures
    # all indicators show NaN during warmup, not misleading values like 0.0.
    lookback = kwargs.get("length")
    if (
        lookback is not None
        and isinstance(result, pd.Series)
        and len(result) > lookback
    ):
        result = result.copy()
        result.iloc[:lookback] = np.nan
    
    return result
```

**Before/after diff (minimal):**
```diff
     if result is None:
         series = args[0] if args else kwargs.get("close")
         if series is not None and isinstance(series, pd.Series):
             return pd.Series(float("nan"), index=series.index, dtype="float64")
         return None
+    
+    lookback = kwargs.get("length")
+    if (
+        lookback is not None
+        and isinstance(result, pd.Series)
+        and len(result) > lookback
+    ):
+        result = result.copy()
+        result.iloc[:lookback] = np.nan
+    
     return result
```

**Verify:**
```python
import pandas as pd
import numpy as np
import math
from finbar_strategy_runtime.indicators._handler_registry import _safe_ta

def fake_rsi(close, length=14):
    """Simulate pandas_ta rsi: returns partial Series for short data."""
    return pd.Series(0.0, index=close.index)

close = pd.Series([100.0 + i for i in range(25)])
result = _safe_ta(fake_rsi, close, length=14)
# First 14 bars must be NaN
assert math.isnan(result.iloc[0])
assert math.isnan(result.iloc[13])
# Bar 14+ must be 0.0 (the fake_rsi value)
assert result.iloc[14] == 0.0
```

---

### Step 2: Run existing tests
**Command:**
```bash
cd packages/strategy-runtime && python -m pytest tests/ -x -q
```

**Expected:** All existing tests pass. Tests that checked RSI values on early bars may need updating (change expected 0.0 → NaN for bars within the warmup period).

---

### Step 3: Integration test via MCP
**Command:**
```json
compute_indicators("ETH", "hyperliquid", "1h",
    '["rsi_14","rsi_7","sma_20","atr"]',
    start_date="2026-06-10")
```

**Verify:**
- `rsi_14`: bars 0–13 = NaN, bar 14+ = valid (0–100)
- `rsi_7`: bars 0–6 = NaN, bar 7+ = valid
- `sma_20`: unchanged (was already NaN for bars 0–19)
- `atr`: unchanged

---

### Step 4: Regression test — no length kwarg
```python
# Callers without length= kwarg should not break
result = _safe_ta(lambda x: x, some_series)  # no length=
assert result is not None
```
