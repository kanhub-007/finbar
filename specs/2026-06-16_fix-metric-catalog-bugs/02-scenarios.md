# Scenarios — Metric Catalog Bug Fixes

---

### Scenario: Fix handler argument mismatch for demand_zone_score
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given ETH-USD daily OHLCV bars are available
  When `compute_indicators` is called with `demand_zone_score` in the indicators list
  Then the `demand_zone_score` column exists in output bars AND contains non-null integer values (0–6)

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| symbol | string | "ETH-USD" | Any cached symbol |
| interval | string | "1d" | Daily or intraday |
| indicators_json | string[] | ["demand_zone_score"] | Must include volume-aware metrics |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| `demand_zone_score` column exists in bars | Inspect returned bar keys |
| Values are ints 0–6 (not NaN) | Check last 3 bars of computation |
| No TypeError raised silently | Job status = completed, no error |

**Verify (Classical school, black-box):**
```python
from finbar_strategy_runtime.domain.services.supply_demand_zones import demand_zone_score

# Simulate 30 bars of OHLCV data
import pandas as pd
import numpy as np
idx = pd.date_range("2026-01-01", periods=30, freq="D")
df = pd.DataFrame({
    "high": np.random.uniform(100, 110, 30),
    "low": np.random.uniform(95, 100, 30),
    "close": np.random.uniform(98, 105, 30),
    "volume": np.random.uniform(1e6, 1e7, 30),
}, index=idx)

result = demand_zone_score(df["high"], df["low"], df["close"], df["volume"])
assert result.notna().any(), "Should have non-null values after warmup"
assert result.iloc[-1] in range(7), f"Value {result.iloc[-1]} not in 0-6"
# Do NOT: mock any domain service
```

**Also test:**
- `supply_zone_score` returns same structure (0–6 ints).
- `zone_failure_bullish` returns boolean Series (not all-null).
- `zone_failure_bearish` returns boolean Series (not all-null).

---

### Scenario: Fix handler argument mismatch for supply_zone_score
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the same data as demand_zone_score
  When `supply_zone_score` is computed
  Then handler passes `volume` as 4th positional arg and returns 0–6 ints

**Verify:**
```python
from finbar_strategy_runtime.domain.services.supply_demand_zones import supply_zone_score
result = supply_zone_score(df["high"], df["low"], df["close"], df["volume"])
assert result.notna().any()
assert result.iloc[-1] in range(7)
```

---

### Scenario: Fix handler argument mismatch for zone_failure_bullish/bearish
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given ETH-USD daily OHLCV bars with volume
  When `zone_failure_bullish` is computed
  Then handler passes `volume` as 4th positional arg and returns boolean Series

**Verify:**
```python
from finbar_strategy_runtime.domain.services.supply_demand_zones import zone_failure_bullish, zone_failure_bearish
bull = zone_failure_bullish(df["high"], df["low"], df["close"], df["volume"])
bear = zone_failure_bearish(df["high"], df["low"], df["close"], df["volume"])
assert isinstance(bull.iloc[-1], (bool, np.bool_))
assert isinstance(bear.iloc[-1], (bool, np.bool_))
```

---

### Scenario: Fix window/lookback mismatch for effective_tick_spread
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given ETH-USD daily OHLCV with 76 bars
  When `effective_tick_spread` is computed via `compute_indicators`
  Then the column exists and contains non-null float values after warmup (bars 60+)

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| symbol | string | "ETH-USD" | At least 60 bars cached |
| interval | string | "1d" | Daily |
| indicators_json | string[] | ["effective_tick_spread"] | |

**Expected output:**
| Assertion | How to verify |
|-----------|---------------|
| Column exists | Inspect returned bar keys |
| Non-null floats at tail | Check last 5 bars; at least some non-NaN |

**Verify:**
```python
from finbar_strategy_runtime.domain.services.spread_proxies import effective_tick_spread

close = pd.Series(np.random.uniform(100, 110, 65))
result = effective_tick_spread(close, lookback=60)
assert result is not None, "Should return float, not None with 65 bars"
assert isinstance(result, float)
# Do NOT: pass lookback=20 and expect it to work
```

**Also test:**
- `lot_zero_return_spread` returns non-null with 60 bars.
- `liu_illiq` returns non-null with 21 bars.
- `resiliency_autocorr` returns non-null with 21 bars.

---

### Scenario: Fix window/lookback mismatch for lot_zero_return_spread
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given 65 daily close prices
  When `lot_zero_return_spread` is called with lookback=60
  Then returns a float (not None)

**Verify:**
```python
from finbar_strategy_runtime.domain.services.spread_proxies import lot_zero_return_spread
close = pd.Series(np.random.uniform(100, 110, 65))
result = lot_zero_return_spread(close, lookback=60)
assert isinstance(result, float)
```

---

### Scenario: Fix window/lookback mismatch for liu_illiq
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given 25 daily volume bars (some non-zero)
  When `liu_illiq` is called with lookback=21
  Then returns proportion of zero-volume days (0.0 for crypto)

**Verify:**
```python
from finbar_strategy_runtime.domain.services.liquidity_proxies import liu_illiq
vol = pd.Series([1e6] * 25)  # crypto: never zero volume
result = liu_illiq(vol, lookback=21)
assert result == 0.0  # no zero-volume days
```

---

### Scenario: Fix window/lookback mismatch for resiliency_autocorr
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given 25 daily close prices
  When `resiliency_autocorr` is called with lookback=20, lag=1
  Then returns a float autocorrelation (not None)

**Verify:**
```python
from finbar_strategy_runtime.domain.services.resiliency_proxies import resiliency_autocorr
close = pd.Series(np.random.uniform(100, 110, 25))
result = resiliency_autocorr(close, lookback=20, lag=1)
assert isinstance(result, float)
assert -1.0 <= result <= 1.0
```

---

### Scenario: Fix proxy computation (proxy_atr, proxy_ib_high/low, proxy_expected_move)
**Priority:** Must
**Slice:** 1

> ⚠️ **Corrected** — see `research/03-verification-and-corrections.md`. The proxy
> handlers in `inside_bar.py` are never dispatched (short-circuited by
> `name.startswith("proxy_")` in the calculator). The fix is in
> `enrich_dataframe_with_proxies`, not the handlers.

**Gherkin:**
  Given ETH-USD daily OHLCV bars
  When `compute_indicators` is called with `["proxy_atr", "proxy_ib_high", "proxy_ib_low", "proxy_expected_move"]` (WITHOUT requesting `atr`)
  Then ALL FOUR columns exist in output AND contain non-null float values after the 14-bar ATR warmup

**Input table:**
| Field | Example | Constraint |
|-------|---------|------------|
| indicators_json | `["proxy_atr","proxy_ib_high","proxy_ib_low","proxy_expected_move"]` | No `atr` requested |

**Expected output:**
| Assertion | How to verify |
|-----------|---------------|
| `proxy_atr` column exists | Inspect bar keys |
| `proxy_ib_high` column exists | Inspect bar keys |
| `proxy_ib_low` column exists | Inspect bar keys |
| `proxy_expected_move` column exists | Inspect bar keys |
| Values non-null after bar 14 | Check tail bars |

**Verify (Classical school, black-box):**
```python
from finbar_strategy_runtime.domain.services.proxy_indicator import enrich_dataframe_with_proxies
import pandas as pd, numpy as np

idx = pd.date_range("2026-01-01", periods=30, freq="D")
df = pd.DataFrame({
    "open": np.random.uniform(100, 110, 30),
    "high": np.random.uniform(108, 115, 30),
    "low": np.random.uniform(95, 102, 30),
    "close": np.random.uniform(100, 110, 30),
    "volume": np.random.uniform(1e6, 1e7, 30),
}, index=idx)

result = enrich_dataframe_with_proxies(df)
for col in ("proxy_atr", "proxy_ib_high", "proxy_ib_low", "proxy_expected_move"):
    assert col in result.columns, f"{col} missing"
    assert not pd.isna(result[col].iloc[-1]), f"{col} null at tail"
# Do NOT: rely on the @_register proxy handlers — they are never dispatched
```

**Also test:**
- Requesting all proxies together still produces every column (no regressions on proxy_vwap, proxy_ibs, etc.)
- `proxy_atr` value is positive and scales with bar range
- `proxy_ib_high` > `proxy_ib_low` for every bar

---

### Scenario: poc_rejection / edge_volume_building intraday — characterization
**Priority:** Must
**Slice:** 1

> ⚠️ **Reclassified after diagnosis (2026-06-16)** — the original
> corrected hypothesis ("an exception is being raised inside
> `compute_amt_signals` on intraday") was **disproven by diagnosis**.
> Random, multi-day, and real-handler-enriched intraday fixtures all
> show `compute_amt_signals` returns clean boolean Series whenever its
> dependencies are present — it does **not** raise. The reproducible
> user-visible symptom ("`poc_rejection` null on all intraday bars") is
> a **dependency-resolution gap**, not an exception: `poc_rejection`
> declares `requires={vp_poc, atr}` and `edge_volume_building` declares
> `requires={vp_vah, vp_val, rvol}`; when those are not co-requested
> the dispatch logs `Missing columns for 'poc_rejection': {...}, wrote
> NaN` and skips the handler. This is the **same bug class as
> `vol_buffer_high`** (research/03 §2) and is handled by the Slice 2
> scenario "check_metric warns on unsatisfied non-OHLCV requires".
>
> This scenario is therefore **characterization only**: pin the actual
> contract (no exception, bool output, non-null when deps present). The
> root-cause fix lands in Slice 2.

**Gherkin:**
  Given ETH-USD 1h OHLCV bars enriched with vp_poc/vp_vah/vp_val, auction state (at_poc, near_vah, near_val), rvol, atr
  When `compute_amt_signals(enriched_df)` is called directly
  Then it returns without raising AND `poc_rejection` / `edge_volume_building` columns contain boolean values

**Verify:**
```python
from finbar_strategy_runtime.domain.services.amt_signals import compute_amt_signals

# Build enriched_df with all required columns populated (no NaN in deps)
result = compute_amt_signals(enriched_df)   # must NOT raise
assert "poc_rejection" in result.columns
assert "edge_volume_building" in result.columns
assert result["poc_rejection"].dtype == bool
assert result["edge_volume_building"].dtype == bool
assert result["poc_rejection"].notna().all(), "no NaN allowed in bool output"
```

**Also test:**
- Via dispatch with deps co-requested, both columns appear with True/False (never null)
- Job logs show no "Failed to compute indicator 'poc_rejection'" warning

> **Root-cause fix:** Slice 2 scenario "check_metric warns on unsatisfied
> non-OHLCV requires" covers `poc_rejection`, `edge_volume_building`,
> `vol_buffer_high`, and any metric whose `requires` extends beyond OHLCV.

---

### Scenario: Update catalog for intraday-only metrics
**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given the METRIC_CATALOG.md documentation
  When a user reads the docs for `ib_high`, `ib_low`, `ib_midpoint`, `ib_range`
  Then the catalog clearly marks them as intraday-only (❌ on daily, ✅ on intraday)

**Expected output:**
| Assertion | How to verify |
|-----------|---------------|
| `ib_high` row shows ❌ for Daily column | Read METRIC_CATALOG.md Section 1 |
| `ib_low` row shows ❌ for Daily | Same |
| `ib_midpoint` row shows ❌ for Daily | Same |
| `ib_range` row shows ❌ for Daily | Same |
| Doc explains why (needs session-scoped first-hour bars) | Footnote or description |

---

### Scenario: Mark data-source-limited metrics as unavailable
**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given `check_metric` is called for `first_last_hour_vol_fraction`
  When the data source is yfinance or Hyperliquid
  Then the response includes a warning that `opening_volume`/`closing_volume` columns are missing

**Verify:**
```python
result = check_metric("first_last_hour_vol_fraction", 
    available_data_class="daily_ohlcv", symbol="ETH-USD")
assert result["computable"] == False
assert any("opening_volume" in w or "closing_volume" in w for w in result["warnings"])
```

---

### Scenario: Update MCP tool descriptions for conditional metrics
**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given `list_market_metrics` or `get_strategy_capabilities` is called
  When a metric is conditional (only works on certain data classes or with sufficient bars)
  Then the description or metadata includes that constraint

**Expected output:**
| Metric | Updated description includes |
|--------|------------------------------|
| `hurst_exponent` | "Requires at least 100 bars" |
| `market_regime` | "Requires at least 220 bars for classification" |
| `trend_phase` | "Returns 'unknown' when no clear phase detected; fires on markup/distribution/accumulation conditions" |
| `trend_direction` | "Returns null when no clear direction detected" |
| `williams_fractal_high/low` | "Requires sufficient price swings; may be null on short histories" |
| `ib_high/low/midpoint/range` | "Intraday only — requires session-scoped data to identify first-hour bars" |
| `vwap_session`, `vwap_upper/lower_1/2` | "Intraday only — session-scoped VWAP" |
| `realized_vol_5m/15m/1h` | "Intraday only — computed from sub-bar returns" |

**Verify:**
```python
# Call list_market_metrics for each conditional metric
metrics = list_market_metrics(interval="1d")
for m in metrics:
    if m["name"] in CONDITIONAL_METRICS:
        assert "requires" in m["description"].lower() or "intraday" in m["description"].lower() or \
               m["computable"] == False, f"{m['name']} should describe constraints"
```

---

### Scenario: Implement proxy for first_last_hour_vol_fraction
**Priority:** Could
**Slice:** 3

**Gherkin:**
  Given ETH-USD 1h OHLCV bars
  When `first_last_hour_vol_fraction` is computed on intraday data
  Then the metric computes fraction from actual first/last hour of each UTC day (not requiring `opening_volume` column)

**Expected output:**
| Assertion | How to verify |
|-----------|---------------|
| Column exists in output | Inspect bar keys |
| Values are floats 0.0–1.0 | Check last 24 bars |
| Computed from volume grouping by date | Code review |

**Verify:**
```python
# The revised function groups 1h bars by UTC date,
# sums volume for hour=0 and hour=23, divides by daily total
# No longer requires external columns
result = first_last_hour_vol_fraction_proxy(intraday_df)
assert result.notna().any()
assert (result >= 0).all() and (result <= 1).all()
```

---

### Scenario: Surface failed indicators in job metadata (observability)
**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given a handler raises an exception during computation
  When the indicator job completes
  Then the job result metadata includes a `failed_indicators` list with (name, error_message) tuples
  And the user can see which metrics failed and why via `get_indicator_job_progress`

**Verify:**
```python
# Temporarily break a handler (e.g. demand_zone_score arg mismatch)
# Run compute_indicators job, poll progress
progress = get_indicator_job_progress(job_id)
assert "failed_indicators" in progress
assert any(name == "demand_zone_score" for name, _ in progress["failed_indicators"])
assert any("volume" in err for _, err in progress["failed_indicators"])
```

**Rationale:** This is the highest-leverage fix. Silent error swallowing
(`except Exception: result[name] = np.nan`) is why all the bugs in this spec
went undetected. Surfacing failures turns silent nulls into visible errors.

---

### Scenario: check_metric warns on unsatisfied non-OHLCV requires
**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given `check_metric` is called for `vol_buffer_high` (which requires `atr`)
  When `atr` is not in the requested indicator set
  Then the response includes a warning that `atr` dependency is not satisfied

**Verify:**
```python
result = check_metric("vol_buffer_high", available_data_class="daily_ohlcv", symbol="ETH-USD")
assert any("atr" in w for w in result.get("warnings", []))
```

**Also test:** `proxy_ib_high`, `breaker_block_bullish` (requires close), `poc_rejection` (requires `vp_poc`, `atr`), `edge_volume_building` (requires `vp_vah`, `vp_val`, `rvol`), and any metric whose `requires` set extends beyond OHLCV.

> **Note:** `poc_rejection` / `edge_volume_building` were originally
> Scenario 9 (Slice 1). Diagnosis disproved the "intraday exception"
> hypothesis — the real cause is this dependency-resolution gap. The
> user-visible fix (warning when deps are not co-requested) lives here.

---

### Scenario: Document minimum bar requirements in catalog
**Priority:** Could
**Slice:** 3

**Gherkin:**
  Given METRIC_CATALOG.md
  When a user reads the entry for `hurst_exponent`
  Then the description includes "Requires ≥100 bars; returns None otherwise"

**Also test:**
- `market_regime`: "Requires ≥220 bars"
- `effective_tick_spread`: "Requires ≥60 bars for lookback window"
- `lot_zero_return_spread`: "Requires ≥60 bars"
