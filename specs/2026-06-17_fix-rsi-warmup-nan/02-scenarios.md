# Scenarios — RSI Warmup NaN Fix

---

### Scenario: rsi_14 returns NaN for first 14 bars
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given ETH-USDC 1h OHLCV bars are available
  When `compute_indicators` is called with `rsi_14`
  Then bars 0–13 have `rsi_14 = NaN` and bar 14+ has a valid RSI value

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| symbol | string | "ETH" | Any cached symbol |
| source | string | "hyperliquid" | Any source |
| interval | string | "1h" | Any interval |
| indicators_json | string[] | ["rsi_14"] | — |

**Expected output:**
| Assertion | How to verify |
|-----------|---------------|
| `rsi_14` is NaN for bars 0–13 | Check first 14 bars of output |
| `rsi_14` is a float (not NaN) for bar 14 | Check bar 14 (0-indexed) |
| `rsi_14` is between 0–100 (not NaN) for bar 20+ | Check bar 20 |
| No `failed_indicators` entry for rsi_14 | Job progress |
| Previous behavior (0.0) no longer occurs | Bar 0–13 must be NaN, not 0.0 |

**Verify (Classical school, black-box):**
```python
# Via MCP
result = compute_indicators("ETH", "hyperliquid", "1h",
    indicators_json='["rsi_14"]',
    start_date="2026-06-10")

# Inspect page 0 (first few bars)
bars_page_0 = get_indicator_job_results(job_id, page=0)

import math
assert math.isnan(bars_page_0["bars"][0]["rsi_14"]), "Bar 0 must be NaN"
assert math.isnan(bars_page_0["bars"][13]["rsi_14"]), "Bar 13 must be NaN"

# Inspect page 3 (bars 15-19)
bars_page_3 = get_indicator_job_results(job_id, page=3)
assert not math.isnan(bars_page_3["bars"][0]["rsi_14"]), "Bar 15 must have value"
assert 0 <= bars_page_3["bars"][0]["rsi_14"] <= 100
```

**Also test:**
- `rsi_7` returns NaN for first 7 bars
- Dynamic `rsi_21` returns NaN for first 21 bars
- `sma_20` still returns NaN for first 20 bars (no regression — already worked)
- `atr` still returns NaN during warmup (no regression)

---

### Scenario: _safe_ta works for callers without length kwarg
**Priority:** Should
**Slice:** 1

**Gherkin:**
  Given a hypothetical `_safe_ta` caller that does NOT pass `length=`
  When `_safe_ta(func, close)` is called
  Then no crash occurs and the original behavior is preserved

**Verify:**
```python
from finbar_strategy_runtime.indicators._handler_registry import _safe_ta
import pandas as pd
import numpy as np

close = pd.Series([100.0, 101.0, 102.0])
# Call without length kwarg — should not crash
result = _safe_ta(lambda x: x, close)  # no length kwarg
assert result is not None
```

---

### Scenario: No regression for already-working indicators
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given any valid OHLCV data
  When `compute_indicators` is called with a mix of indicators (sma_20, atr, macd, rsi_14)
  Then sma_20, atr, and macd produce identical values to before the fix

**Verify:**
```python
# Compare pre-fix and post-fix output for non-RSI indicators
# sma_20, atr, macd — already NaN during warmup, should be unchanged
# rsi_14 — changed from 0.0 to NaN during warmup, same values after warmup
```

---

### Scenario: Dynamic rsi_N also gets warmup mask
**Priority:** Should
**Slice:** 1

**Gherkin:**
  Given a parameterized RSI like `rsi_21`
  When computed via dynamic dispatch
  Then first 21 bars are NaN

**Verify:**
```python
compute_indicators("ETH", "hyperliquid", "1h",
    indicators_json='["rsi_21"]',
    start_date="2026-06-10")
# Bar 0–20: NaN, Bar 21+: valid RSI
```

**Note:** Dynamic dispatch (`_compute_dynamic`) also calls `_safe_ta` with `length=period`, so this is covered automatically.
