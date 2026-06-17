# Implementation Guide — Hurst Minimum Bars to 250

---

### Step 1: Raise default in hurst_exponent signature
**File:** `packages/strategy-runtime/finbar_strategy_runtime/domain/services/hurst_regime.py`

Change line ~16:
```python
def hurst_exponent(
    close: pd.Series,
    min_bars: int = 100,    # ← OLD
```
to:
```python
def hurst_exponent(
    close: pd.Series,
    min_bars: int = 250,    # ← NEW
```

**Verify:**
```python
from finbar_strategy_runtime.domain.services.hurst_regime import hurst_exponent
import inspect
sig = inspect.signature(hurst_exponent)
assert sig.parameters["min_bars"].default == 250
```

---

### Step 2: Raise default in fractal_regime signature
**File:** `packages/strategy-runtime/finbar_strategy_runtime/domain/services/hurst_regime.py`

Change line ~97:
```python
def fractal_regime(
    close: pd.Series,
    min_bars: int = 100,    # ← OLD
```
to:
```python
def fractal_regime(
    close: pd.Series,
    min_bars: int = 250,    # ← NEW
```

**Verify:** Same as Step 1 for `fractal_regime`.

---

### Step 3: Update catalog metadata
**File:** `packages/strategy-runtime/finbar_strategy_runtime/parser/_metric_data.py`

Around line 983–991, change:
```python
MarketMetricDefinition(
    name="hurst_exponent",
    family=MetricFamily.PRICE_ACTION,
    description="Hurst exponent for trend persistence vs mean-reversion.",
    required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
    required_columns=("close",),
    min_lookback=100,                                                   # ← OLD
    confidence=MetricConfidence.PROXY,
    condition_note="Requires at least 100 bars; returns None otherwise.",  # ← OLD
),
```
to:
```python
MarketMetricDefinition(
    name="hurst_exponent",
    family=MetricFamily.PRICE_ACTION,
    description="Hurst exponent for trend persistence vs mean-reversion.",
    required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
    required_columns=("close",),
    min_lookback=250,                                                   # ← NEW
    confidence=MetricConfidence.PROXY,
    condition_note="Requires at least 250 bars; returns None otherwise.",  # ← NEW
),
```

**Verify:**
```python
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog
catalog = UnifiedMetricCatalog()
hurst = catalog.get("hurst_exponent")
assert hurst.min_lookback == 250
```

---

### Step 4: Run existing tests
**Command:**
```bash
cd packages/strategy-runtime && python -m pytest tests/ -x -q -k "hurst"
```

**Expected:** Tests that use <250 bars and expect a valid H value will now fail and need updating (increase test data to 250+ bars).

**Common mistake:** Forgetting to update test fixtures that assume 100-bar minimum. Any test with <250 bars that asserts `hurst_exponent is not None` must be updated.

---

### Step 5: Integration test via MCP
**Command:**
```json
// With 180 bars → all NaN
compute_indicators("ETH", "hyperliquid", "1h",
    '["hurst_exponent","fractal_regime"]',
    start_date="2026-06-10")
// → hurst_exponent = NaN (all bars), fractal_regime = "unknown"

// With 500+ bars → real values
compute_indicators("ETH", "hyperliquid", "1h",
    '["hurst_exponent","fractal_regime"]',
    start_date="2026-05-01")
// → hurst_exponent ≈ 0.5–0.6 (broadcast), fractal_regime = "TRENDING" | "RANDOM" | "MEAN_REVERTING"
```

---

### Step 6: Update documentation
**File:** `docs/METRIC_CATALOG.md` §7 (Bill Williams / Chaos Theory)

Update the `hurst_exponent` row description from:
```
H<0.5 = mean-reverting, H=0.5 = random, H>0.5 = trending. Requires ≥100 bars; returns None otherwise
```
to:
```
H<0.5 = mean-reverting, H=0.5 = random, H>0.5 = trending. Full-series broadcast (not rolling). Requires ≥250 bars; returns None otherwise.
```
