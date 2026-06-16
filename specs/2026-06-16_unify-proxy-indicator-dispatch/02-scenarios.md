# Scenarios — Unify Proxy Indicator Dispatch

All scenarios use **Classical (Detroit) school + black-box** tests: real
`PandasTaIndicatorCalculator`, real `UnifiedMetricCatalog`, deterministic
fixtures. Assert on **outcomes** (which columns appear, non-null tails,
check_metric results), never on which internal methods ran.

The defining behaviour change vs. today: **requesting one proxy returns
only that column** (today it returns all 12).

---

### Scenario 1: Requesting a single proxy returns only that column
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given an OHLCV frame and a request for `["proxy_vwap"]`
  When  `calculate()` runs
  Then  the result contains `proxy_vwap`
  And   the result does NOT contain `proxy_atr`, `proxy_ibs`,
        `proxy_parkinson`, etc.

**Input table:**
| Field       | Type | Example                          |
|-------------|------|----------------------------------|
| indicators  | list | `["proxy_vwap"]`                 |
| frame       | df   | 30-bar OHLCV, no `atr` column    |

**Expected output / state change:**
| Assertion                                         | How to verify              |
|---------------------------------------------------|----------------------------|
| `"proxy_vwap" in result.columns`                  | inspect columns            |
| `"proxy_atr" not in result.columns`               | inspect columns            |
| `"proxy_ibs" not in result.columns`               | inspect columns            |
| `"proxy_parkinson" not in result.columns`         | inspect columns            |

**Verify (Classical school, black-box):**
```python
result = calc.calculate(df, ["proxy_vwap"])
assert "proxy_vwap" in result.columns
for other in ("proxy_atr", "proxy_ibs", "proxy_parkinson",
              "proxy_garman_klass", "proxy_ib_high"):
    assert other not in result.columns, f"{other} leaked into request"
```

**Also test:**
- Requesting two proxies returns exactly those two.
- Requesting a proxy alongside a non-proxy (e.g. `["sma_20", "proxy_vwap"]`)
  returns `sma_20` + `proxy_vwap` and nothing else proxy.

---

### Scenario 2: Every proxy is independently computable (no ordering dependency)
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given each of the 12 proxy names requested alone
  When  `calculate()` runs for each
  Then  each produces its own column with non-null values after warmup

**Input table:**
| Field      | Type | Example                                                  |
|------------|------|----------------------------------------------------------|
| proxy_name | str  | one of the 12 registered proxy names                     |
| frame      | df   | 40-bar OHLCV (clears the 14-bar ATR warmup)              |

**Expected output / state change:**
| Assertion                                         | How to verify              |
|---------------------------------------------------|----------------------------|
| `proxy_name in result.columns`                    | inspect columns            |
| `result[proxy_name].tail(5).notna().any()`        | non-null after warmup      |

**Verify (Classical school, black-box):**
```python
ALL_PROXIES = [
    "proxy_atr", "proxy_vwap", "proxy_ibs", "proxy_ib_high", "proxy_ib_low",
    "proxy_expected_move", "proxy_iv", "proxy_parkinson", "proxy_garman_klass",
    "proxy_rogers_satchell", "proxy_typical_price", "proxy_ohlc4",
]
for name in ALL_PROXIES:
    result = calc.calculate(df_40bar, [name])
    assert name in result.columns
    assert result[name].tail(5).notna().any(), f"{name} all-null at tail"
```

**Also test:**
- The ATR cluster (`proxy_ib_high`, `proxy_ib_low`, `proxy_expected_move`,
  `proxy_iv`) each compute correctly when requested alone — i.e. they do
  NOT depend on `proxy_atr` being co-requested.

---

### Scenario 3: ATR-dependent proxies share computation when co-requested
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a request for `["proxy_atr", "proxy_ib_high"]`
  When  `calculate()` runs
  Then  both columns are present and non-null
  And   the Wilder-RMA ATR is computed exactly once (MACD-style cache)

**Input table:**
| Field       | Type | Example                              |
|-------------|------|--------------------------------------|
| indicators  | list | `["proxy_atr", "proxy_ib_high"]`     |

**Expected output / state change:**
| Assertion                                         | How to verify                       |
|---------------------------------------------------|-------------------------------------|
| both columns present + non-null at tail           | inspect columns + tail              |
| ATR computed once (shared via per-call cache)      | code review / cache-key assertion   |

**Verify (Classical school, black-box):**
```python
result = calc.calculate(df_40bar, ["proxy_atr", "proxy_ib_high"])
assert result["proxy_atr"].tail(5).notna().any()
assert result["proxy_ib_high"].tail(5).notna().any()
# Correctness: proxy_ib_high == open + 0.1 * proxy_atr
import numpy as np
tail = result.tail(10)
np.testing.assert_allclose(
    tail["proxy_ib_high"], tail["open"] + 0.1 * tail["proxy_atr"], rtol=1e-12,
)
```

**Note:** "computed once" is verified by code review (the cache helper) and
by the parity of values — if ATR were recomputed independently the values
would still match (same deterministic formula), so the cache is a
performance/DRY concern, not a correctness one. Do NOT assert call counts
on domain objects (Classical school).

---

### Scenario 4: check_metric is honest for all 12 proxies by construction
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given all 12 proxies are registered in the METRICS registry
  When  `check_metric` is called for each
  Then  each reports `computable=True` on a supported data class
  And   the construction-time consistency check passes (handler == registry)

**Input table:**
| Field      | Type | Example                              |
|------------|------|--------------------------------------|
| proxy_name | str  | one of the 12                        |

**Expected output / state change:**
| Assertion                                         | How to verify              |
|---------------------------------------------------|----------------------------|
| `catalog.check(name, "daily_ohlcv").computable`   | True for OHLCV-only proxy |
| construction-time `_validate_consistency` passes  | catalog instantiates       |

**Verify (Classical school, black-box):**
```python
catalog = UnifiedMetricCatalog()  # raises if registry/handlers disagree
for name in ALL_PROXIES:
    result = catalog.check(name, "daily_ohlcv")
    assert result.computable is True, f"{name}: {result.warnings}"
```

**Also test:**
- The 3 previously-hidden proxies (`proxy_typical_price`, `proxy_ohlc4`,
  `proxy_iv`) are now discoverable via `list_market_metrics`.

---

### Scenario 5: ATR-dependent handlers do not declare requires={"atr"}
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the corrected handler registrations
  When  `proxy_ib_high` is requested WITHOUT `atr` and WITHOUT `proxy_atr`
  Then  it computes successfully (non-null) because it derives ATR internally

**Verify (Classical school, black-box):**
```python
# Request proxy_ib_high alone — must not need pandas_ta 'atr'.
result = calc.calculate(df_40bar, ["proxy_ib_high"])
assert result["proxy_ib_high"].tail(5).notna().any()
# And must NOT have pulled in an 'atr' column as a side effect.
assert "atr" not in result.columns
```

**Rationale:** the dead handlers in `inside_bar.py` declared
`requires={"atr"}` (pandas_ta ATR). Under per-handler dispatch that would
make them fail when `atr` isn't co-requested. They must instead derive
ATR from OHLCV via the shared helper (ADR-3).

---

### Scenario 6: No proxy short-circuit remains in the calculator
**Priority:** Should
**Slice:** 1

**Gherkin:**
  Given the refactored calculator
  When  the source is inspected
  Then  there is no `name.startswith("proxy_")` branch
  And   proxies dispatch through the same `elif name in _INDICATOR_HANDLERS` path as all other metrics

**Verify (structural):**
```python
import inspect
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)
src = inspect.getsource(PandasTaIndicatorCalculator.calculate)
assert "proxy_" not in src or "startswith" not in src  # no short-circuit
# _compute_proxies helper removed OR repurposed (no longer on dispatch path)
```

**Also test:** the only remaining use of `enrich_dataframe_with_proxies`
from the calculator package is gone (it stays for single-bar enrichment
only).

---

### Scenario 7: Existing proxy behaviour preserved for legitimate callers
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a strategy that legitimately requests a set of proxies together
  When  `calculate()` runs
  Then  all requested proxies are present and correct (no regression)

**Verify (Classical school, black-box):**
```python
# A representative multi-proxy request (the Slice-1 metric-catalog scenario 8)
result = calc.calculate(df_40bar, [
    "proxy_atr", "proxy_ib_high", "proxy_ib_low", "proxy_expected_move",
])
for name in ("proxy_atr", "proxy_ib_high", "proxy_ib_low", "proxy_expected_move"):
    assert name in result.columns
    assert result[name].tail(5).notna().any()
assert (result["proxy_ib_high"] > result["proxy_ib_low"]).tail(20).all()
```

**Also test:**
- `enrich_bar_with_proxies` (single-bar) still works unchanged.
- The order-independence property from Slice-1 scenario 8 still holds
  (requesting `proxy_ib_high` before vs after `atr` gives the same proxy
  value, since proxies no longer touch the `atr` column at all).

---

### Scenario 8: Catalog documentation lists all 12 proxies
**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given METRIC_CATALOG.md
  When  a user reads the proxy section
  Then  all 12 proxy names are documented with their data-class support

**Verify (docs-drift test):**
```python
# Parse METRIC_CATALOG.md; assert each of ALL_PROXIES appears in a table row.
```

**Also test:** the 3 previously-hidden proxies are explained
(typical_price, ohlc4, iv-from-ATR).
