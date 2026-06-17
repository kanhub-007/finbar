# Implementation Guide — Metric Catalog Bug Fixes

---

### Step 1: Fix supply/demand zone handler argument mismatches
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/handlers/price_action.py`

Fix 4 handlers that pass only 3 args but need 4 (missing `volume`):

```python
# BEFORE (broken):
@_register("demand_zone_score", requires={"high", "low", "close"})
def _h_dz_score(df, _name, _cache):
    df["demand_zone_score"] = _dz_score(df["high"], df["low"], df["close"])
    return df

# AFTER (fixed):
@_register("demand_zone_score", requires={"high", "low", "close", "volume"})
def _h_dz_score(df, _name, _cache):
    df["demand_zone_score"] = _dz_score(df["high"], df["low"], df["close"], df["volume"])
    return df
```

Apply the same fix to: `_h_sz_score`, `_h_zf_bull`, `_h_zf_bear`.

**Verify:** Run the job from Scenario 1 via MCP and check that columns appear with non-null values.

**Common mistake:** Forgetting to update `requires={"..., \"volume\"}"` in the decorator — without it, the dependency resolver may skip the handler if volume wasn't explicitly requested.

---

### Step 2: Fix rolling_scalar_series window mismatches
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/handlers/microstructure.py`

The `rolling_scalar_series` wrapper passes a 20-bar window, but the functions need larger lookbacks. Fix by passing explicit windows that match the function defaults:

```python
# BEFORE:
df["effective_tick_spread"] = rolling_scalar_series(_et_calc, df["close"])

# AFTER:
df["effective_tick_spread"] = rolling_scalar_series(_et_calc, df["close"], window=60)
```

| Handler | Fix |
|---------|-----|
| `_h_effective_tick` | `window=60` (matches `_et_calc` default `lookback=60`) |
| `_h_lot_spread` | `window=60` (matches `_lot_calc` default `lookback=60`) |
| `_h_liu` | `window=21` (matches `_liu` default `lookback=21`) |
| `_h_res_auto` | `window=21` (function needs `lookback=20 + lag=1 = 21`) |

**Future-proofing:** Consider extracting window from function signature defaults:
```python
import inspect
default_lookback = inspect.signature(_et_calc).parameters["lookback"].default
df["effective_tick_spread"] = rolling_scalar_series(_et_calc, df["close"], window=default_lookback)
```

**Verify:** Run Scenario 4-7 tests. Check that metrics return non-null values after their respective warmup periods (60 bars for spreads, 21 for liu/resiliency).

**Common mistake:** Setting window too large (e.g., 100) — this increases warmup but doesn't break correctness. Too small is the problem.

---

> ⚠️ **CORRECTED after verification pass** — see `research/03-verification-and-corrections.md`.
> The original Steps 3 & 4 assumed proxy handlers are dispatched. They are NOT.
> The `name.startswith("proxy_")` short-circuit in `pandas_ta_indicator_calculator.py:89`
> routes ALL proxy names to `enrich_dataframe_with_proxies()` directly, making the
> registered proxy handlers in `inside_bar.py` dead code.

### Step 3: Add missing proxy computations to enrich_dataframe_with_proxies
**File:** `packages/strategy-runtime/finbar_strategy_runtime/domain/services/proxy_indicator.py`

**Root cause (verified):** In `pandas_ta_indicator_calculator.py` the dispatch loop has:
```python
for name in indicators:
    if name.startswith("proxy_"):
        result = _compute_proxies(result, cache)   # ← ALL proxies go here
    elif name in _INDICATOR_HANDLERS:
        ...   # ← registered proxy handlers NEVER reach this branch
```
`_compute_proxies()` calls `enrich_dataframe_with_proxies(df)` and nothing else.
The 8 `@_register` proxy handlers in `inside_bar.py` are **dead code**: they populate
`_INDICATOR_HANDLERS` (which makes `check_metric` lie — see Step 7b) but are never
invoked. Therefore `proxy_atr` (only computed by the dead handler) is always missing,
and `proxy_ib_high/low/expected_move` (computed by `enrich_dataframe_with_proxies`
only `if "atr" in result.columns`) are missing because `atr` is never injected.

**Fix (Option B — matches the actual execution path):** Add the missing computations
directly to `enrich_dataframe_with_proxies()` so they always run:

```python
def enrich_dataframe_with_proxies(df: Any) -> Any:
    result = df.copy()
    h = result["high"]; l = result["low"]; c = result["close"]; o = result["open"]

    # ... existing proxy_typical_price, proxy_ohlc4, proxy_vwap, proxy_ibs,
    #     proxy_parkinson, proxy_garman_klass, proxy_rogers_satchell ...

    # NEW: always compute proxy_atr (Wilder RMA) so dependents work unconditionally
    prev_close = c.shift(1).fillna(c)
    tr = pd.concat([h - l, (h - prev_close).abs(), (l - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    result["proxy_atr"] = atr

    # NEW: proxy_ib_high/low/expected_move now always computable (no atr dependency)
    result["proxy_ib_high"] = o + 0.1 * atr
    result["proxy_ib_low"] = o - 0.1 * atr
    result["proxy_expected_move"] = 0.8 * atr
    result["proxy_iv"] = np.where(c > 0, (atr / c) * math.sqrt(TRADING_DAYS_PER_YEAR), 0.0)

    return result
```

**Also:** Remove the now-redundant `if "atr" in result.columns:` conditional block
that previously gated these computations.

**Verify:** Run Scenario 8 via MCP — request `proxy_ib_high`, `proxy_ib_low`,
`proxy_expected_move` WITHOUT requesting `atr`. All 3 columns (plus `proxy_atr`)
must appear with non-null values after the 14-bar ATR warmup.

---

### Step 4: Delete dead proxy handlers
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/handlers/inside_bar.py`

Delete the 8 proxy handlers (lines ~108-152) that are never dispatched:
`_proxy_atr`, `_proxy_vwap`, `_proxy_ibs`, `_proxy_ib_high`, `_proxy_ib_low`,
`_proxy_expected_move`, `_proxy_parkinson`, `_proxy_garman_klass`, `_proxy_rogers_satchell`.

**Why:** They are dead code. Their only effect is to register names in
`_INDICATOR_HANDLERS`, which makes `check_metric` report them as computable
(see `unified_metric_catalog.py:361`) even when the computation lives entirely
in `enrich_dataframe_with_proxies`. Removing them makes `check_metric` honest.

**Keep:** The `ib_high`, `ib_low`, `ib_midpoint`, `ib_range` handlers and the
VWAP bands code at the bottom of the file — those ARE dispatched normally.

**Verify:** After deletion, run the existing test suite. `check_metric("proxy_atr")`
should still resolve (the name is recognised by the parser catalog) and the
computation should now actually produce the column.

**Alternative (Option A — NOT recommended):** Instead of deleting the handlers,
remove the `name.startswith("proxy_")` short-circuit in `pandas_ta_indicator_calculator.py`
so the handlers dispatch normally, then make each handler self-contained
(compute its own ATR). More work, more surface area, no benefit over Option B.

---

### Step 5: Diagnose and fix poc_rejection / edge_volume_building intraday exception
**File:** `packages/strategy-runtime/finbar_strategy_runtime/domain/services/amt_signals.py` (likely) and/or `indicators/handlers/market_profile_amt.py`

> ⚠️ **CORRECTED** — original hypothesis (cache ordering) was wrong.

**Verified facts:**
- The audit output showed `poc_rejection: null` and `edge_volume_building: null` (JSON null = pandas NaN) on ALL 1493 intraday bars.
- `_poc_rejection` and `_edge_volume_building` return boolean Series (True/False), never NaN.
- NaN in the output can ONLY come from the dispatch's exception handler in
  `pandas_ta_indicator_calculator.py`: `except Exception: result[name] = np.nan`.
- Therefore `compute_amt_signals(df)` (or the surrounding `_compute_amt_signals`
  handler) is **raising an exception** on intraday data.

**Diagnosis step (do this BEFORE writing a fix):**
1. Build a small intraday fixture (e.g. 200 1h bars of ETH-USD) with `vp_poc`,
   `vp_vah`, `vp_val`, `at_poc`, `near_vah`, `near_val`, `rvol`, `atr`, `close`
   already populated.
2. Call `compute_amt_signals(fixture)` directly in a Python REPL.
3. Read the full traceback.

**Candidate causes to check in the traceback:**
- `_value_area_migration` accesses `df.index.date` — if `classify_auction_state`
  returned a frame whose index was reset or is not a `DatetimeIndex`, `.date`
  raises `AttributeError`.
- `_poc_rejection` does `atr.isna().all()` — if `atr` is present but has
  `dtype=object` (mixed types from a merge), `.isna()` may behave unexpectedly.
- The cache mechanism: if `acceptance_into_value` runs first and its call to
  `compute_amt_signals` raises, the cache key is never set, but partial columns
  may be left in an inconsistent state.

**Fix:** Apply the targeted fix indicated by the traceback. Do NOT guess.

**Verify:** Run Scenario 10 with intraday data. Both `poc_rejection` and
`edge_volume_building` must contain boolean values (True OR False, never NaN).
Also check the job logs contain no "Failed to compute indicator" warnings for
any AMT signal.

---

### Step 6: Implement proxy for first_last_hour_vol_fraction
**File:** `packages/strategy-runtime/finbar_strategy_runtime/domain/services/intraday_seasonality_proxies.py`

Replace the current implementation that requires `opening_volume`/`closing_volume` columns with one that groups by UTC date:

```python
def first_last_hour_vol_fraction_proxy(df: pd.DataFrame) -> pd.Series:
    """Fraction of volume in first and last hour of each UTC day.
    
    Groups intraday bars by UTC date, sums volume for hours 0 and 23,
    divides by daily total volume. Uses the index's hour component.
    
    For daily bars: returns NaN (cannot subdivide).
    """
    idx = df.index
    if not hasattr(idx, 'hour'):
        return pd.Series(np.nan, index=idx)
    
    result = pd.Series(np.nan, index=idx)
    date_groups = idx.to_series().dt.date
    
    for date, mask in date_groups.groupby(date_groups).groups.items():
        day_bars = df.loc[mask]
        hour = day_bars.index.hour
        first_hour_vol = day_bars.loc[hour == hour.min(), "volume"].sum()
        last_hour_vol = day_bars.loc[hour == hour.max(), "volume"].sum()
        total_vol = day_bars["volume"].sum()
        if total_vol > 0:
            fraction = (first_hour_vol + last_hour_vol) / total_vol
            result.loc[mask] = fraction
    
    return result
```

**Update handler registration** in `microstructure.py`:
```python
@_register("first_last_hour_vol_fraction", requires={"volume"})
def _h_flhvf(df, _name, _cache):
    df["first_last_hour_vol_fraction"] = _flhvf_proxy(df)
    return df
```

**Verify:** Run Scenario 12 with intraday data.

---

### Step 7: Update METRIC_CATALOG.md
**File:** `docs/METRIC_CATALOG.md`

Update the following rows:

**Family 1 (Traditional TA), `ib_high/low/midpoint/range`:**
```
| `ib_high` | Session | ❌ | ✅ | Initial Balance high (first-hour range). Intraday only — requires session-scoped data. |
```

**Family 18 (Derivatives)** — add note:
```
> ⚠️ All derivatives metrics require COINGLASS_API_KEY and prior `fetch_derivatives` call.
> Not computable from yfinance or Hyperliquid OHLCV alone.
```

**Family 20 (Volume):**
```
| `volume_to_trade_count_proxy` | ⚠️ | ⚠️ | Crude proxy: `volume ÷ 500`. No real trade count data. |
```

---

### Step 8: Update MCP tool descriptions for conditional metrics
**Files:** `packages/strategy-runtime/finbar_strategy_runtime/parser/_metric_registry.py` and/or `unified_metric_catalog.py`

Add `bar_requirement` and `data_class_requirement` fields to metric definitions:

```python
# For metrics with minimum bar requirements:
{
    "name": "hurst_exponent",
    "bar_requirement": 100,
    "description": "Hurst exponent via R/S analysis. Requires >= 100 bars."
}

# For intraday-only metrics:
{
    "name": "vwap_session",
    "data_class_requirement": "intraday_ohlcv",
    "description": "Session-scoped VWAP with daily reset. Intraday only."
}

# For conditional metrics:
{
    "name": "trend_phase",
    "condition_note": "Returns 'unknown' when no clear phase is detected",
    "description": "Classifies trend as markup/distribution/accumulation. Returns 'unknown' in neutral markets."
}
```

Then update `list_market_metrics` response to include these fields when non-null, and update `check_metric` to report warnings:

```python
def check_metric(name, available_data_class, **kwargs):
    # ...
    if metric.get("bar_requirement") and available_bar_count < metric["bar_requirement"]:
        warnings.append(f"Requires {metric['bar_requirement']} bars; only {available_bar_count} available")
    if metric.get("data_class_requirement") and available_data_class != metric["data_class_requirement"]:
        warnings.append(f"Requires {metric['data_class_requirement']}; currently {available_data_class}")
    if metric.get("condition_note"):
        description += f" ({metric['condition_note']})"
```

**Verify:** Call `list_market_metrics` and `check_metric` for each conditional metric; verify warnings appear in response.

---

### Step 8b: Stop silently swallowing handler exceptions
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/pandas_ta_indicator_calculator.py`

**Root cause of undetected bugs:** Lines 99-110 catch every handler exception
and convert to NaN with only a `logger.warning`. This is why the
`demand_zone_score` TypeError and the AMT intraday exception went unnoticed.

**Fix (minimal):** Collect failed indicators into the cache and expose them
in the job result so they're visible via `get_indicator_job_progress`:

```python
cache: dict[str, pd.DataFrame] = {}
failed: list[tuple[str, str]] = []   # NEW: (indicator_name, error_message)
...
try:
    result = handler(result, name, cache)
except Exception as exc:
    result[name] = np.nan
    failed.append((name, str(exc)))   # NEW
    logger.warning("Failed to compute indicator '%s'", name, exc_info=True)
...
# At end of calculate():
if failed:
    cache["__failed_indicators"] = failed   # job runner reads this
```

The job runner should then surface `failed_indicators` in the progress/result
metadata so users (and the LLM) see which metrics failed and why.

**Verify:** Temporarily reintroduce the `demand_zone_score` arg bug and confirm
it now appears in `get_indicator_job_progress` output as a failed indicator
with the TypeError message, not just a silent NaN.

---

### Step 9: Run full regression test
**File:** N/A (test run)

After all fixes, re-run the MCP verification audit against ETH-USD daily + hourly:

```python
# Same test as the original audit:
# 1. Fetch daily and hourly data
# 2. Compute ALL metrics in batch jobs
# 3. Verify every metric column exists and has non-null values at tail
# 4. Cross-reference against catalog documentation
```

**Expected outcome:**
- 🔴 Bug count drops from 14 → 0
- ⚠️ Always-null count drops from 17 → ~5 (remainder are expected: insufficient bars, intraday-only on daily query)
- `check_metric` warnings appear for conditional metrics
- Catalog documentation matches runtime behavior

**Verify:** Run `pytest tests/` in strategy-runtime package.

**Common mistake:** Not re-running the full audit. Individual fixes may interact — the proxy copy fix (Step 4) could affect the zone handler fixes (Step 1) if dispatch ordering changes.
