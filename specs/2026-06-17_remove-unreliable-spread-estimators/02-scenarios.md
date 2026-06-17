# Scenarios — Remove Unreliable Spread Estimators

---

### Scenario: corwin_schultz_spread not computable via MCP
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the handler registration is removed
  When `compute_indicators` is called with `corwin_schultz_spread`
  Then the job reports "Unknown indicator name" and writes a NaN column

**Verify:**
```python
result = compute_indicators("AAPL", "yfinance", "1d",
    indicators_json='["corwin_schultz_spread"]',
    start_date="2026-04-01")

# Assert:
# - failed_indicators contains ("corwin_schultz_spread", "Unknown indicator name")
# - Column exists but all NaN
```

---

### Scenario: corwin_schultz_spread not in list_market_metrics
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the catalog entry is removed
  When `list_market_metrics` is called
  Then `corwin_schultz_spread`, `abdi_ranaldo_spread`, `chung_zhang_spread` are absent

**Verify:**
```python
metrics = list_market_metrics("AAPL", "yfinance", "1d")
names = {m["name"] for m in metrics}
assert "corwin_schultz_spread" not in names
assert "abdi_ranaldo_spread" not in names
assert "chung_zhang_spread" not in names
```

---

### Scenario: Remaining spread estimators still work
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the three unreliable estimators are unregistered
  When `fong_holden_tran_spread`, `roll_spread`, `effective_tick_spread`, `lot_zero_return_spread` are requested
  Then they compute normally with no regression

**Verify:**
```python
result = compute_indicators("AAPL", "yfinance", "1d",
    indicators_json='["fong_holden_tran_spread","roll_spread","effective_tick_spread","lot_zero_return_spread"]',
    start_date="2026-04-01")

# Assert:
# - fong_holden_tran_spread ≈ 0.024
# - roll_spread ≈ 0.015–0.017
# - No failed_indicators for these four
```

---

### Scenario: Domain functions still importable
**Priority:** Should
**Slice:** 1

**Gherkin:**
  Given the handler registrations are removed
  When `from finbar_strategy_runtime.domain.services.spread_proxies import corwin_schultz_spread` is executed
  Then the import succeeds and the function is callable

**Verify:**
```python
from finbar_strategy_runtime.domain.services.spread_proxies import (
    corwin_schultz_spread,
    abdi_ranaldo_spread,
    chung_zhang_spread,
)
# Import succeeds — functions still exist for internal consumers
```

---

### Scenario: Internal consumers not broken
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given `spread_based_pin_proxy` and `resiliency_spread_to_impact` import domain functions directly
  When those compound metrics are computed
  Then they still produce output (even if degraded by 0.0 spread input)

**Verify:**
```python
# These should still compute without ImportError
result = compute_indicators("AAPL", "yfinance", "1d",
    indicators_json='["spread_based_pin_proxy","resiliency_spread_to_impact"]',
    start_date="2026-04-01")
# Assert no ImportError or NameError in failed_indicators
```

---

### Scenario: Docs no longer list the three estimators
**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given METRIC_CATALOG.md §8 and QUANTITATIVE_PROXIES.md §2
  When a reader looks at available spread estimators
  Then `corwin_schultz_spread`, `abdi_ranaldo_spread`, `chung_zhang_spread` are absent from tables

**Verify:**
```bash
grep "corwin_schultz_spread\|abdi_ranaldo_spread\|chung_zhang_spread" docs/METRIC_CATALOG.md
# No table rows for these three
grep "corwin_schultz_spread\|abdi_ranaldo_spread\|chung_zhang_spread" docs/QUANTITATIVE_PROXIES.md
# No references (or only in a "previously available" changelog section if desired)
```
