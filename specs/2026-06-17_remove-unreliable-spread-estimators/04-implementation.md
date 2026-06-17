# Implementation Guide — Remove Unreliable Spread Estimators

---

### Step 1: Remove handler registrations
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/handlers/microstructure.py`

Remove the three import aliases (lines 13–15):
```python
# REMOVE:
    abdi_ranaldo_spread as _ar_calc,
    chung_zhang_spread as _cz_calc,
    corwin_schultz_spread as _cs_calc,
```

Remove the three handler functions (lines 78–81, 88–91, 108–111):
```python
# REMOVE all three blocks:

@_register("corwin_schultz_spread", requires={"open", "high", "low", "close"})
def _h_corwin_schultz(df, _name, _cache):
    df["corwin_schultz_spread"] = _cs_calc(df)
    return df

@_register("abdi_ranaldo_spread", requires={"open", "high", "low", "close"})
def _h_abdi_ranaldo(df, _name, _cache):
    df["abdi_ranaldo_spread"] = _ar_calc(df)
    return df

@_register("chung_zhang_spread", requires={"open", "high", "low", "close"})
def _h_chung_zhang(df, _name, _cache):
    df["chung_zhang_spread"] = _cz_calc(df)
    return df
```

**Verify:** No import errors on module load.

---

### Step 2: Remove catalog entries
**File:** `packages/strategy-runtime/finbar_strategy_runtime/parser/_metric_data.py`

Remove the three `MarketMetricDefinition` blocks (around lines 20–36, 40–54, 71–85):
```python
# REMOVE all three blocks:

MarketMetricDefinition(
    name="corwin_schultz_spread",
    family=MetricFamily.SPREAD,
    ...
),

MarketMetricDefinition(
    name="abdi_ranaldo_spread",
    family=MetricFamily.SPREAD,
    ...
),

MarketMetricDefinition(
    name="chung_zhang_spread",
    family=MetricFamily.SPREAD,
    ...
),
```

**Verify:**
```python
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog
catalog = UnifiedMetricCatalog()
assert catalog.get("corwin_schultz_spread") is None
assert catalog.get("fong_holden_tran_spread") is not None  # still there
```

---

### Step 3: Remove compound metric reference (if any)
**File:** `packages/strategy-runtime/finbar_strategy_runtime/parser/_metric_registry.py`

Check line ~120 for `corwin_schultz_spread` reference in a compound metric resolver. If it's a fallback chain for the conceptual `spread` metric, replace with `fong_holden_tran_spread` or `roll_spread`.

**Verify:** `check_metric("spread", ...)` still resolves to a working estimator.

---

### Step 4: Update tests
Run and fix all failing tests:
```bash
cd packages/strategy-runtime && python -m pytest tests/ -x -q -k "corwin or abdi or chung"
```

Expected failures (tests to update):
- `test_indicator_handlers_microstructure.py` — remove the three from expected columns
- `test_market_metric_catalog.py` — remove `corwin_schultz_spread` assertions
- `test_unified_catalog.py` — remove `corwin_schultz_spread` from known-handled lists
- `test_parser_accepts_new_metrics.py` — remove `test_corwin_schultz_spread_accepted`
- `test_api_metrics.py` — remove `test_list_includes_corwin_schultz`
- `test_mcp_metrics_catalog.py` — remove `corwin_schultz_spread` reference
- `test_check_metric_capability.py` — remove the test case

**Keep unchanged:**
- `test_microstructure_calculators.py` — tests domain functions directly, not handlers

---

### Step 5: Full test suite
```bash
cd packages/strategy-runtime && python -m pytest tests/ -x -q
```

---

### Step 6: Update documentation
**Files:** `docs/METRIC_CATALOG.md` §8, `docs/QUANTITATIVE_PROXIES.md` §2

Remove the three rows from the spread estimators table. Optionally add a changelog note: "Removed `corwin_schultz_spread`, `abdi_ranaldo_spread`, `chung_zhang_spread` (2026-06-17) — unreliable for single-asset use. Use `fong_holden_tran_spread` or `roll_spread` instead."

---

### Step 7: Integration test via MCP
```json
// These should now produce "Unknown indicator name"
compute_indicators("AAPL", "yfinance", "1d",
    '["corwin_schultz_spread","abdi_ranaldo_spread","chung_zhang_spread"]')

// These should still work
compute_indicators("AAPL", "yfinance", "1d",
    '["fong_holden_tran_spread","roll_spread","effective_tick_spread","lot_zero_return_spread"]')
```
