# Scenarios — Hurst Minimum Bars to 250

---

### Scenario: hurst_exponent returns None with < 250 bars
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a price series with fewer than 250 returns
  When `hurst_exponent(close)` is called with default arguments
  Then it returns `None` (not a noisy float)

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| close | pd.Series | 180 values | len(close) < 251 |
| min_bars | int | (default) | Default is now 250 |

**Expected output:**
| Assertion | How to verify |
|-----------|---------------|
| Returns `None` for 180 bars | Unit test with 180-bar series |
| Returns `None` for 249 bars | Unit test with 249-bar series |
| Returns a float for 250 bars | Unit test with 250-bar synthetic series |
| Returns a float for 1000 bars | Unit test with 1000-bar series |

**Verify (Classical school, black-box):**
```python
from finbar_strategy_runtime.domain.services.hurst_regime import hurst_exponent
import pandas as pd
import numpy as np

# 180 bars → None
rng = np.random.default_rng(42)
prices = 100 + np.cumsum(rng.normal(0, 1, 180))
close = pd.Series(prices)
assert hurst_exponent(close) is None

# 250 bars → float
prices = 100 + np.cumsum(rng.normal(0, 1, 251))
close = pd.Series(prices)
h = hurst_exponent(close)
assert isinstance(h, float)
assert 0.2 < h < 0.8  # Reasonable range for random walk
```

**Also test:**
- `fractal_regime(close)` returns `"unknown"` for < 250 bars
- `hurst_exponent(close, min_bars=50)` still works (explicit override respected)
- Broadcast handler returns NaN-filled Series when < 250 bars

---

### Scenario: MCP compute_indicators returns null for hurst_exponent with 180 bars
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given ETH-USDC 1h OHLCV bars (180 bars, as in the audit)
  When `compute_indicators` is called with `hurst_exponent`
  Then the `hurst_exponent` column is all-NaN (not 0.5976 broadcast)

**Verify:**
```python
# Via MCP
compute_indicators("ETH", "hyperliquid", "1h",
    indicators_json='["hurst_exponent"]',
    start_date="2026-06-10")

# Assert:
# - hurst_exponent column exists
# - All values are NaN (not 0.5976)
# - No failed_indicators entry for hurst_exponent
```

---

### Scenario: MCP compute_indicators returns valid H with 500+ bars
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a dataset with 500+ bars
  When `hurst_exponent` is computed
  Then it returns a single non-NaN value broadcast to all bars

**Verify:**
```python
# Fetch longer history
fetch_price_history("ETH", "1h", "hyperliquid", start_date="2026-05-01")

compute_indicators("ETH", "hyperliquid", "1h",
    indicators_json='["hurst_exponent"]',
    start_date="2026-05-01")

# Assert:
# - All bars have same non-NaN hurst_exponent value
# - Value is in [0, 1] range
```

---

### Scenario: check_metric reports computable=false for small datasets
**Priority:** Should
**Slice:** 1

**Gherkin:**
  Given a symbol with fewer than 250 cached bars
  When `check_metric("hurst_exponent", ...)` is called
  Then computable = false, condition_note mentions 250-bar minimum

**Verify:**
```python
check_metric("hurst_exponent", available_data_class="intraday_ohlcv", symbol="ETH")
# → computable: false (if < 250 bars cached)
# → condition_note includes "250"
```

---

### Scenario: list_market_metrics shows min_lookback=250
**Priority:** Should
**Slice:** 1

**Gherkin:**
  Given any valid symbol
  When `list_market_metrics` is called
  Then the `hurst_exponent` entry shows `min_lookback: 250`

**Verify:**
```python
metrics = list_market_metrics("ETH", "hyperliquid", "1h")
hurst = next(m for m in metrics if m["name"] == "hurst_exponent")
assert hurst["min_lookback"] == 250
assert "250" in hurst.get("condition_note", "")
```

---

### Scenario: Explicit min_bars override still works
**Priority:** Could
**Slice:** 2

**Gherkin:**
  Given a caller who explicitly passes `min_bars=50`
  When `hurst_exponent(close, min_bars=50)` is called with 100 bars
  Then it returns a float (honoring the explicit override)

**Verify:**
```python
prices = 100 + np.cumsum(np.random.default_rng(0).normal(0, 1, 100))
close = pd.Series(prices)
h = hurst_exponent(close, min_bars=50)
assert isinstance(h, float)  # Explicit override → 50 is enough
```
