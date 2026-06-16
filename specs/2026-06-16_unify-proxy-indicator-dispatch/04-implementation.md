# Implementation Guide — Unify Proxy Indicator Dispatch

Ordered steps. Each step ends with a `Verify` command. Follow
Red → Green → Refactor: write the scenario's failing test first.

All tests live under `packages/strategy-runtime/tests/contract/`
(parallel to the metric-catalog bug-fix tests) plus a few in
`tests/test_infrastructure/` and `tests/test_docs/`.

---

### Step 1: Extract per-proxy compute functions + the ATR cache helper
**File:** `finbar_strategy_runtime/domain/services/proxy_indicator.py`

The formulas already exist in `enrich_dataframe_with_proxies`; extract
them into individually-callable functions so handlers can call one each.
Keep `enrich_dataframe_with_proxies` working (single-bar path uses it)
but have it delegate to the extracted functions (DRY).

Add the ATR cache helper:

```python
_PROXY_ATR_CACHE_KEY = "__proxy_atr"


def compute_proxy_atr(df: pd.DataFrame) -> pd.Series:
    """Wilder RMA ATR (14-period) from high/low/close — pure computation."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1).fillna(close)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()


def ensure_proxy_atr(df: pd.DataFrame, cache: dict) -> pd.Series:
    """Return the cached ATR, computing + caching it if absent (MACD pattern)."""
    if _PROXY_ATR_CACHE_KEY in cache:
        return cache[_PROXY_ATR_CACHE_KEY]
    atr = compute_proxy_atr(df)
    cache[_PROXY_ATR_CACHE_KEY] = atr
    return atr
```

Extract one function per proxy column (`compute_proxy_vwap(df)`,
`compute_proxy_ibs(df)`, `compute_proxy_parkinson(df)`, etc.) returning
a `pd.Series`. Refactor `enrich_dataframe_with_proxies` to call them.

**Verify:** existing `tests/test_domain/test_proxy_indicator.py` still
passes (the `enrich_dataframe_with_proxies` output is unchanged).
**Common mistake:** changing the `proxy_iv` formula — keep
`(atr / close) * sqrt(252)` exactly as-is.

---

### Step 2: Replace dead handlers with 12 real, self-contained handlers
**File:** `finbar_strategy_runtime/indicators/handlers/inside_bar.py`

Delete the 9 dead `_proxy_*` functions (lines ~91–152). Add 12 real
handlers, each writing only its own column:

```python
@_register("proxy_vwap", requires={"high", "low", "close"})
def _h_proxy_vwap(df, _name, _cache):
    df["proxy_vwap"] = (df["high"] + df["low"] + df["close"]) / 3.0
    return df

@_register("proxy_atr", requires={"high", "low", "close"})
def _h_proxy_atr(df, _name, cache):
    df["proxy_atr"] = ensure_proxy_atr(df, cache)
    return df

@_register("proxy_ib_high", requires={"open", "high", "low", "close"})
def _h_proxy_ib_high(df, _name, cache):
    atr = ensure_proxy_atr(df, cache).fillna(0)
    df["proxy_ib_high"] = df["open"] + 0.1 * atr
    return df
# ... proxy_ib_low, proxy_expected_move, proxy_iv, proxy_ibs,
#     proxy_parkinson, proxy_garman_klass, proxy_rogers_satchell,
#     proxy_typical_price, proxy_ohlc4
```

**Critical:** the ATR-cluster handlers declare `requires` = OHLCV columns
only (open/high/low/close), **never** `atr`. They derive ATR via
`ensure_proxy_atr`. (Scenario 5.)

**Verify:** Scenarios 2, 3, 5.
**Common mistake:** forgetting `fillna(0)` on the ATR Series before the
`open + 0.1*atr` arithmetic — leaves NaN during the 14-bar warmup where
today's code returns 0 (see Slice-1 scenario 8 fix).

---

### Step 3: Remove the short-circuit from the calculator
**File:** `finbar_strategy_runtime/indicators/pandas_ta_indicator_calculator.py`

Delete the `if name.startswith("proxy_"):` branch and the
`_compute_proxies` helper. Proxies now flow through the existing
`elif name in _INDICATOR_HANDLERS:` path. Keep the `FAILED_INDICATORS_ATTR`
observability wiring (Scenario 4 of the metric-catalog spec) — it already
covers the standard handler path.

**Verify:** Scenario 1 (request scope) + Scenario 6 (no short-circuit).
**Common mistake:** leaving `_PROXY_CACHE_KEY` referenced anywhere — the
per-call `cache` still exists, but the old proxy sentinel is gone.

---

### Step 4: Register all 12 proxies in the METRICS registry
**File:** `finbar_strategy_runtime/parser/_metric_registry.py`

Add `MarketMetricDefinition` entries for the 3 currently-missing proxies
(`proxy_typical_price`, `proxy_ohlc4`, `proxy_iv`) and verify the other
9 are present. All 12:

```python
MarketMetricDefinition(
    name="proxy_typical_price",
    family=MetricFamily.VOLATILITY,   # or a new PROXY family — see ADR-4
    description="VWAP proxy: (H+L+C)/3.",
    required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
    required_columns=("high", "low", "close"),
    min_lookback=1,
    confidence=MetricConfidence.PROXY,
),
# ... proxy_ohlc4 (requires open,high,low,close),
#     proxy_iv (requires high,low,close; condition_note "annualised ATR% / sqrt(252)")
```

Add the 3 missing names to `strategy_indicator_catalog._FIXED` so the
parser accepts them.

**Verify:** Scenario 4 (check_metric honest for all 12). The
construction-time `_validate_consistency` will fail loud if any registry
entry lacks a handler (or vice versa) — that's the safety net.
**Common mistake:** giving an ATR-cluster proxy `required_columns`
that omits a column its handler actually reads (e.g. `proxy_ib_high`
needs `open` too, not just high/low/close).

---

### Step 5: Update tests that leaned on get-all-proxies
**File:** `tests/test_infrastructure/test_indicator_calculator.py:82`

The test `test_proxy_indicators` requests `["proxy_typical_price",
"proxy_ibs"]` and asserts `proxy_parkinson` is present. Under exact
request scope that assertion now fails. Update it to assert only the
requested columns, OR explicitly request all proxies it inspects.

```python
# BEFORE:
result = self.calc.calculate(df, ["proxy_typical_price", "proxy_ibs"])
assert "proxy_parkinson" in result.columns   # relied on get-all
# AFTER:
result = self.calc.calculate(df, ["proxy_typical_price", "proxy_ibs"])
assert "proxy_typical_price" in result.columns
assert "proxy_ibs" in result.columns
assert "proxy_parkinson" not in result.columns  # exact scope
```

**Verify:** `pytest tests/test_infrastructure/test_indicator_calculator.py -q`.
Audit every other proxy reference (use `grep -rn "proxy_" tests/`) for the
same assumption before running the full suite.

---

### Step 6: Update catalog docs + add docs-drift test
**File:** `docs/METRIC_CATALOG.md`

Document all 12 proxies in the proxy section (Section 19). Add the 3
previously-hidden ones with their formulas.

**File:** `tests/test_docs/test_metric_catalog_proxy_docs.py` — parse
the markdown, assert each of the 12 names appears in a table row.

**Verify:** Scenario 8.

---

### Step 7: Full regression + the cross-spec parity note
**Verify:**
```bash
# Package contract suite (zero exclusions — the crossover fix is in)
cd packages/strategy-runtime && .venv/Scripts/python.exe -m pytest tests/contract/ -q
# Root suite
cd .. && .venv/Scripts/python.exe -m pytest tests/ -q
```

Confirm the Slice-1 metric-catalog proxy tests (scenario 8) still pass —
they request the 4 ATR-cluster proxies together, which now dispatch as 4
separate handlers sharing the cached ATR. Values must be identical.

Add a one-line note to the streaming-indicator-calculator spec's
`03-domain.md` classifier section: "proxy names now resolve via the
standard handler registry (post 2026-06-16 unify-proxy-dispatch); no
special-case branch needed."
