# Scenarios — Fix IB Handler NameError

---

### Scenario: ib_high computes correctly on intraday data
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given ETH-USDC 1h OHLCV bars are available from Hyperliquid
  When `compute_indicators` is called with `ib_high` in the indicators list
  Then the `ib_high` column exists in output bars AND contains non-null float values for bars after the first session

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| symbol | string | "ETH" | Any cached symbol with intraday data |
| source | string | "hyperliquid" | Any source with intraday bars |
| interval | string | "1h" | Any intraday interval |
| indicators_json | string[] | ["ib_high"] | At minimum ib_high |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| `ib_high` column exists in bars | Inspect returned bar keys |
| `ib_high` is non-null for bars after first session | Check bars on day 2+ |
| `ib_high` ≈ max(high of first N bars of each day) | Cross-check with raw high values |
| No NameError in `failed_indicators` | Job status = completed, no error for ib_high |

**Verify (Classical school, black-box):**
```python
# After fix, compute IB on ETH 1h data via MCP
compute_indicators("ETH", "hyperliquid", "1h",
    indicators_json='["ib_high","ib_low","ib_range","ib_midpoint"]',
    start_date="2026-06-10")

# Assert:
# - Job has no failed_indicators for ib_high/ib_low/ib_range/ib_midpoint
# - Bars on day 2 have non-null ib_high values
# - ib_high on a given day == max(high of first N bars of that day)
#   where N = 1 for 1h (first hour = first bar)
```

**Also test:**
- `ib_low` returns non-null values (min of first N bars)
- `ib_range` returns non-null values (ib_high - ib_low)
- `ib_midpoint` returns non-null values ((ib_high + ib_low) / 2)
- All four IB metrics return null for the very first session (not enough bars to determine session boundary)
- All four IB metrics are constant within each calendar day (broadcast behavior)

---

### Scenario: ib_high with all four IB metrics requested together
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given ETH-USDC 1h OHLCV bars
  When all four IB metrics are requested in a single `compute_indicators` call
  Then all four columns exist, no redundant computation occurs (ib_cache sentinel), and values are internally consistent

**Verify:**
```python
compute_indicators("ETH", "hyperliquid", "1h",
    indicators_json='["ib_high","ib_low","ib_range","ib_midpoint"]',
    start_date="2026-06-10")

# Assert:
# - ib_range == ib_high - ib_low (within float tolerance)
# - ib_midpoint == (ib_high + ib_low) / 2
# - ib_high >= ib_low for every bar
# - All four are NaN on bars before first full session
```

---

### Scenario: ib_high remains not-computable on daily data
**Priority:** Should
**Slice:** 1

**Gherkin:**
  Given ETH-USDC daily OHLCV bars
  When `list_market_metrics` or `check_metric` queries ib_high for interval "1d"
  Then computable = false, confidence = "unavailable"

**Verify:**
```python
check_metric("ib_high", available_data_class="daily_ohlcv", symbol="ETH")
# → computable: false, confidence: "unavailable"
```

---

### Scenario: Dead constants removed from trend_breakout.py (optional cleanup)
**Priority:** Could
**Slice:** 2

**Gherkin:**
  Given the fix is applied to inside_bar.py
  When we inspect trend_breakout.py lines 153–155
  Then the _IB_BARS_MAP, _DEFAULT_IB_BARS, _IB_MINUTES_MAP constants at module level are removed (dead code)

**Verify:**
```bash
grep -n "_IB_BARS_MAP\|_IB_MINUTES_MAP\|_DEFAULT_IB_BARS" \
  packages/strategy-runtime/finbar_strategy_runtime/indicators/handlers/trend_breakout.py
# → No output (constants removed)
```
