# Implementation Guide — Integrate New Market Metrics

Ordered by slice. Each step has: the file to create/modify, the code structure,
the verify command, and common mistakes.

> **Naming convention:** All new OHLCV metrics use the calculator function name
> verbatim as the indicator name (e.g. `corwin_schultz_spread`, `fib_618_retrace`).
> Derivatives metrics use the entity field names (`funding_rate`, `open_interest`).

---

## Slice 1 — Foundation

### Step 1.1: Extract the static metric registry
**File:** `packages/strategy-runtime/finbar_strategy_runtime/parser/_metric_registry.py` (new)

Move the `_METRICS` and `_CONCEPTUAL_METRICS` lists OUT of
`static_market_metric_catalog.py` into this module so the new unified catalog
can import them without pulling in the old class.

```python
"""Static registry of all market metric definitions (data only)."""
from finbar_strategy_runtime.domain.entities.market_metric_definition import MarketMetricDefinition
# ... all the MarketMetricDefinition(...) entries from the old file ...

METRICS: list[MarketMetricDefinition] = [ ... ]
CONCEPTUAL_METRICS: list[MarketMetricDefinition] = [ ... ]
```

**Verify:** `python -c "from finbar_strategy_runtime.parser._metric_registry import METRICS; print(len(METRICS))"`
**Common mistake:** Do NOT import `StaticMarketMetricCatalog` here — that would create a cycle. This module is pure data.
**DataClass enum location:** String values like `"daily_ohlcv"`, `"intraday_ohlcv"` must match the `DataClass` enum at `finbar_strategy_runtime/domain/entities/data_class.py` exactly. Always import `DataClass` and use `DataClass.DAILY_OHLCV` etc. in the registry — never bare strings.

### Step 1.2: Create the unified catalog
**File:** `packages/strategy-runtime/finbar_strategy_runtime/parser/unified_metric_catalog.py` (new)

Implements BOTH `IndicatorCapabilityProvider` (parser-side) and
`MarketMetricCatalog` (capability-side).

```python
"""UnifiedMetricCatalog — single source of truth for metric names + capabilities."""

from finbar_strategy_runtime.parser._metric_registry import METRICS, CONCEPTUAL_METRICS
from finbar_strategy_runtime.domain.entities.metric_capability_result import MetricCapabilityResult
from finbar_strategy_runtime.domain.entities.metric_confidence import MetricConfidence
from finbar_strategy_runtime.domain.interfaces.indicator_capability_provider import IndicatorCapabilityProvider
from finbar_strategy_runtime.domain.interfaces.market_metric_catalog import MarketMetricCatalog

# Names that have handlers registered (populated in Step 1.4).
# A metric is computable only if its name is here AND data class matches.
_HANDLED_NAMES: set[str] = set()


def register_handler(name: str) -> None:
    """Called by @_register to tell the catalog a handler exists."""
    _HANDLED_NAMES.add(name)


class UnifiedMetricCatalog(IndicatorCapabilityProvider, MarketMetricCatalog):
    """Merges parser whitelist + capability registry."""

    def __init__(self) -> None:
        self._by_name = {m.name: m for m in METRICS + CONCEPTUAL_METRICS}

    # --- parser-side (IndicatorCapabilityProvider) ---
    def resolve(self, indicator_type, period): ...   # as before
    def requires_period(self, indicator_type): ...
    def accepts_period(self, indicator_type): ...
    def supports_concrete(self, name): ...            # True if name in _by_name
    def supported_concrete_names(self): ...
    def as_dict(self): ...

    # --- capability-side (MarketMetricCatalog) ---
    def get(self, name): ...
    def list(self, family=None): ...
    def check(self, name, available_data_class) -> MetricCapabilityResult:
        # MUST cross-reference _HANDLED_NAMES (Invariant #4: confidence honesty)
        ...
    def resolve_best(self, concept, available_data_class, interval="1d", force_proxy=False):
        ...

    # --- helper for Invariant #1 (name-sync test) ---
    def all_metric_names(self) -> set[str]:
        """Return every catalogued metric name (for the name-sync test)."""
        return set(self._by_name.keys())
```

**Note:** `all_metric_names()` is NOT on either ABC interface — it is a
concrete method on `UnifiedMetricCatalog` used only by the name-sync test
(Scenario 1.3). Add it directly to the class, not to the interface.

**Verify:** `pytest tests/contract/test_unified_catalog.py -v`
**Common mistake:** Do NOT duplicate the `_make_result` logic — factor it into a private method and have `check()` consult `_HANDLED_NAMES` so an entry with `implemented=True` but no handler still reports `computable=False`.

### Step 1.3: Wire @_register to inform the catalog
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/pandas_ta_indicator_calculator.py` (modify)

Change the `_register` decorator to call `register_handler(name)` so the catalog
knows which names have real compute handlers.

```python
from finbar_strategy_runtime.parser.unified_metric_catalog import register_handler

def _register(name: str, requires: set[str] | None = None):
    def decorator(func):
        _INDICATOR_HANDLERS[name] = (func, requires or set())
        register_handler(name)   # ← NEW: tells the catalog this name is handled
        return func
    return decorator
```

**Verify:** Run any existing indicator test — must still pass. Then run scenario 1.3.
**Common mistake:** Importing `unified_metric_catalog` at module top of `pandas_ta_indicator_calculator` may cause a cycle if the catalog imports anything from `indicators/`. If so, do the `register_handler` import INSIDE the decorator function (deferred import).

### Step 1.4: Create the rolling-window wrapper
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/rolling_scalar_wrapper.py` (new)

```python
"""Convert a scalar calculator into a per-bar Series via rolling window."""
import numpy as np
import pandas as pd


def rolling_scalar_series(calculator, close, window=20, **kwargs) -> pd.Series:
    """Apply a scalar calculator over a trailing window at each bar.

    Args:
        calculator: A function returning a scalar (float | None).
        close: pd.Series — the primary input (used for index + slicing).
        window: Trailing bar count (≥ 2).
        **kwargs: Extra args passed to the calculator.

    Returns:
        pd.Series aligned to `close.index`. First `window-1` bars are NaN.
    """
    n = len(close)
    result = pd.Series(np.nan, index=close.index, dtype="float64")
    for i in range(window - 1, n):
        slice_ = close.iloc[i - window + 1 : i + 1]
        try:
            value = calculator(slice_, **kwargs)
        except Exception:
            value = None
        if value is not None and not (isinstance(value, float) and np.isnan(value)):
            result.iloc[i] = float(value)
    return result
```

**Verify:** `pytest tests/contract/test_rolling_wrapper.py -v` (scenario 1.2)
**Common mistake:** Some scalar calculators take a DataFrame, not a Series (e.g. `corwin_schultz_spread(ohlc)`). For those, build a mini-DataFrame from the window slice inside the handler — don't force every calculator through one wrapper signature.

### Step 1.5: Update finbar re-export shims, THEN remove old catalogs
**Order matters:** update the shims FIRST, then delete the old files.

**Files to update first:**
- `finbar/core/application/services/strategy_indicator_catalog.py` — change the import to point at `finbar_strategy_runtime.parser.unified_metric_catalog.UnifiedMetricCatalog`
- Any test that imports `StaticMarketMetricCatalog` — point at `UnifiedMetricCatalog`

**Files to delete AFTER shims are updated:**
- `packages/strategy-runtime/finbar_strategy_runtime/domain/services/static_market_metric_catalog.py`
- `packages/strategy-runtime/finbar_strategy_runtime/parser/strategy_indicator_catalog.py`

**Verify:** `pytest tests/ -q` — full package suite green.
**Common mistake:** The `finbar/core/application/services/strategy_indicator_catalog.py` shim must point at the new path. Grep for the old import paths.

---

## Slice 2 — Microstructure Handlers

For EACH domain service module, add a handler section to
`pandas_ta_indicator_calculator.py`. Pattern (showing spread_proxies as example):

### Step 2.1: Spread proxies (7 handlers)
**File:** `pandas_ta_indicator_calculator.py` (modify — append handlers)

```python
from finbar_strategy_runtime.domain.services.spread_proxies import (
    corwin_schultz_spread as _cs_calc,
    roll_spread as _roll_calc,
    # ...
)
from finbar_strategy_runtime.indicators.rolling_scalar_wrapper import rolling_scalar_series


@_register("corwin_schultz_spread", requires={"open", "high", "low", "close"})
def _corwin_schultz_spread(df, _name, _cache):
    df["corwin_schultz_spread"] = _cs_calc(df, lookback=20)
    return df


@_register("roll_spread", requires={"close"})
def _roll_spread(df, _name, _cache):
    # Scalar calculator → rolling wrapper
    df["roll_spread"] = rolling_scalar_series(_roll_calc, df["close"], window=20)
    return df
```

Repeat for: `abdi_ranaldo_spread`, `effective_tick_spread` (scalar),
`fong_holden_tran_spread`, `chung_zhang_spread`, `lot_zero_return_spread` (scalar).

**Verify:** `pytest tests/contract/test_indicator_handlers_microstructure.py -k spread -v`
**Common mistake:** For DataFrame-taking calculators (`corwin_schultz_spread(ohlc)`), pass `df` directly — don't slice. For Series-taking ones (`roll_spread(close)`), pass `df["close"]`.

### Steps 2.2–2.10: Remaining microstructure handlers

Apply the same pattern, grouped by module:

| Step | Module | Handlers | Notes |
|------|--------|----------|-------|
| 2.2 | volatility_estimators | close_to_close_vol, parkinson_vol, garman_klass_vol, rogers_satchell_vol, yang_zhang_vol, gk_plus_overnight_vol, meilijson_vol, daily_return_skewness, daily_return_kurtosis | All take Series/DataFrame, return Series |
| 2.3 | liquidity_proxies | amihud_illiq, amivest_liquidity, florackis_lambda, hasbrouck_daily_lambda, liu_illiq (scalar), bao_pan_zhou_cost (scalar) | **`turnover` is NOT registered** — it needs `shares_outstanding` which has no data source in OHLCV. Mark it `implemented=False` in the catalog with description "requires shares_outstanding (not available from OHLCV)". |
| 2.4 | order_flow_proxies | signed_sqrt_volume_ofi, cumulative_signed_volume_ofi, bvc_buy_volume, bvc_sell_volume, bvc_ofi, return_volume_correlation | All take DataFrame |
| 2.5 | informed_trading_proxies | daily_vpin, spread_based_pin_proxy | Take DataFrame |
| 2.6 | jump_risk_proxies | jump_gap_proxy, extreme_return_flag, cc_rs_jump_proxy, overnight_gap_proxy | Mix of DataFrame + Series |
| 2.7 | resiliency_proxies | resiliency_autocorr (scalar), resiliency_spread_to_impact, inverse_amihud_resiliency | |
| 2.8 | intraday_seasonality_proxies | overnight_return, intraday_return (from overnight_intraday_decomp), parametric_u_shape, first_last_hour_vol_fraction | `overnight_intraday_decomp` returns a **tuple of two Series** — register as `overnight_return` (first element) and `intraday_return` (second element). The handler calls the function once and writes both columns. |
| 2.9 | order_arrival_proxies | volume_to_trade_count_proxy, trade_count_daily | |
| 2.10 | information_share_proxies | cross_price_leadership (scalar, needs 2 assets!), volume_weighted_is (scalar), opening_price_leadership (scalar), daily_cross_correlation, daily_beta_ols | Cross-asset metrics need a benchmark — see Step 2.11 |

**Verify after each step:** `pytest tests/contract/test_indicator_handlers_microstructure.py -k <module> -v`

### Step 2.11: Cross-asset metrics (information_share) — DEFERRED

**Decision: Option B — defer to a later spec.** These 5 metrics
(`cross_price_leadership`, `volume_weighted_is`, `opening_price_leadership`,
`daily_cross_correlation`, `daily_beta_ols`) need a second asset's price
series, which the dispatcher has no concept of (no `benchmark_symbol`
parameter exists on indicator jobs). Mark them `implemented=False` in the
catalog with description "requires benchmark asset — see future cross-asset
spec". Do NOT register handlers for them in this spec.

### Step 2.12: Write contract tests for all microstructure handlers
**File:** `tests/contract/test_indicator_handlers_microstructure.py` (new)

One parametrized test per module verifying the column appears + basic sanity
(non-negative for spreads, finite for volatility). Follow scenario 2.1.

**Verify:** `pytest tests/contract/test_indicator_handlers_microstructure.py -v`

---

## Slice 3 — Price-Action Handlers

Same pattern as Slice 2. Group by module:

| Step | Module | Handlers |
|------|--------|----------|
| 3.1 | fibonacci_levels | fib_382_retrace, fib_500_retrace, fib_618_retrace, fib_1618_extension, fib_confluence_score |
| 3.2 | bill_williams_indicators | awesome_oscillator, accelerator_oscillator, alligator_lines (returns 3!), alligator_status, williams_fractal_high, williams_fractal_low, zone_signal |
| 3.3 | trend_structure | swing_high_n, swing_low_n, hh_hl_pattern, lh_ll_pattern, volume_trend_confirmation, trend_phase |
| 3.4 | smc_price_action | bullish_fvg, bearish_fvg, bullish_order_block, bearish_order_block, breaker_block_bullish, breaker_block_bearish, liquidity_sweep_high, liquidity_sweep_low, bos, choch, premium_discount_zone |
| 3.5 | vsa_signals | no_demand, no_supply, stopping_volume, climax_volume, effort_to_rise, effort_to_fall, effort_result_divergence, bag_holding, shakeout, vsa_test_signal |
| 3.6 | supply_demand_zones | demand_zone_low, demand_zone_high, demand_zone_score, supply_zone_low, supply_zone_high, supply_zone_score, zone_failure_bullish, zone_failure_bearish |
| 3.7 | hurst_regime | hurst_exponent (scalar), fractal_regime (returns str!) |
| 3.8 | market_regime | market_regime (returns str Series), day_type_classification (returns str Series) |

**Special cases:**
- `alligator_lines` returns a 3-tuple → register as `alligator_jaw`, `alligator_teeth`, `alligator_lips`.
- `hurst_exponent` is scalar → use `rolling_scalar_series`.
- `fractal_regime`, `market_regime`, `day_type_classification`, `premium_discount_zone`, `trend_phase`, `zone_signal`, `alligator_status` return **categorical strings** → the handler must write an `object`-dtype column (the evaluator's `_resolve_operand` handles strings via `to_numeric` mapping; add the new category strings to `indicator_value_mapper._CATEGORICAL_MAP`).

**Verify after each step:** `pytest tests/contract/test_indicator_handlers_price_action.py -k <module> -v`
**Common mistake:** For categorical metrics, also update `indicator_value_mapper._CATEGORICAL_MAP` so timeframe merging can convert the strings. Without this, merged categorical columns become `None`.

### Step 3.9: Write contract tests for all price-action handlers
**File:** `tests/contract/test_indicator_handlers_price_action.py` (new)

**Verify:** `pytest tests/contract/test_indicator_handlers_price_action.py -v`
**At end of Slice 3:** run the full suite: `pytest tests/ -q` — MVP complete.

---

## Slice 4 — MCP/API Discovery

### Step 4.1: MCP catalog tools
**File:** `finbar/presentation/mcp/tools/metrics_catalog.py` (new)

```python
"""MCP tools exposing the unified metric catalog."""
import json
from fastmcp import FastMCP
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog


def register_metric_catalog_tools(mcp: FastMCP) -> None:
    catalog = UnifiedMetricCatalog()

    @mcp.tool(name="list_market_metrics", description="List all catalogued metrics with computability.")
    def list_market_metrics(symbol: str = "", source: str = "", interval: str = "1d", family: str = "") -> str:
        data_class = "intraday_ohlcv" if interval not in ("1d", "1w") else "daily_ohlcv"
        items = catalog.list(family or None)
        payload = [ { "name": m.name, "family": m.family.value,
                      "computable": catalog.check(m.name, data_class).computable,
                      "confidence": catalog.check(m.name, data_class).confidence.value,
                      "description": m.description } for m in items ]
        return json.dumps(payload, indent=2)

    @mcp.tool(name="check_metric", description="Check if a single metric is computable.")
    def check_metric(name: str, available_data_class: str = "daily_ohlcv") -> str: ...

    @mcp.tool(name="resolve_metric", description="Dual-path resolution for a conceptual metric.")
    def resolve_metric(concept: str, available_data_class: str, interval: str = "1d", force_proxy: bool = False) -> str: ...
```

**Verify:** `pytest tests/test_presentation/test_mcp_metrics_catalog.py -v`
**Common mistake:** Instantiate the catalog ONCE at registration (it's stateless). Don't create a new one per tool call.

### Step 4.2: Register the tools
**File:** `finbar/startup/mcp.py` (modify)

```python
from finbar.presentation.mcp.tools.metrics_catalog import register_metric_catalog_tools
# in the bootstrap:
register_metric_catalog_tools(mcp)
```

### Step 4.3: API routes
**File:** `finbar/presentation/api/routes/metrics.py` (new) + register in `finbar/presentation/api/routes/__init__.py`.

Thin routes mirroring the MCP tools — delegate to `UnifiedMetricCatalog`.

**Verify:** `pytest tests/test_presentation/test_api_metrics.py -v`

---

## Slice 5 — Derivatives Merge

### Step 5.1: Make `interval_offset` public + derivatives merger

First, make the offset function public so the merger can reuse it:

**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/bar_merger.py` (modify)

Rename `_interval_offset` → `interval_offset` (remove underscore). Update
the one internal caller (`_availability_index`). Add it to `__all__` if the
module has one. This is a package-internal rename — no finbar shim changes
needed since the function was private.

**Verify:** `python -c "from finbar_strategy_runtime.indicators.bar_merger import interval_offset; print(interval_offset('1h'))"`

Then create the merger:

**File:** `finbar/infrastructure/services/derivatives_merger.py` (new)

```python
"""No-lookahead as-of merge of derivatives data onto OHLCV bars."""
from __future__ import annotations
import pandas as pd
from finbar.core.domain.entities.derivatives_metrics import DerivativesMetrics

# All nullable float fields on DerivativesMetrics that can become columns.
_DERIVATIVES_COLUMNS = [
    "open_interest", "open_interest_delta_1h", "open_interest_delta_24h",
    "cumulative_volume_delta", "funding_rate", "long_short_ratio",
    "liquidations_long_1h", "liquidations_short_1h",
    "liquidations_long_24h", "liquidations_short_24h",
]


def merge_derivatives_asof(
    ohlcv_df: pd.DataFrame,
    derivatives_rows: list[DerivativesMetrics],
    interval: str = "1h",
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Merge derivatives rows onto the OHLCV frame with no lookahead.

    A derivatives row timestamped T is available only at bar T + interval.
    Reuses the proven offset logic from bar_merger.interval_offset.

    Args:
        ohlcv_df: OHLCV DataFrame with a DatetimeIndex.
        derivatives_rows: list[DerivativesMetrics] from the repository.
        interval: Bar interval (e.g. "1h", "1d").
        columns: Which fields to merge. Defaults to all derivatives columns.

    Returns:
        The ohlcv_df with derivatives columns added (NaN where no data).
    """
    target_cols = columns or _DERIVATIVES_COLUMNS
    result = ohlcv_df.copy()

    if not derivatives_rows:
        # Invariant #2: column must exist even when empty (all-NaN, not absent)
        for col in target_cols:
            result[col] = pd.Series(dtype="float64", index=result.index)
        return result

    # Build availability index: each row's timestamp + interval offset
    from finbar_strategy_runtime.indicators.bar_merger import interval_offset
    offset = interval_offset(interval)
    timestamps = pd.to_datetime([r.timestamp for r in derivatives_rows])
    availability = pd.DatetimeIndex(timestamps + offset)

    # Build a frame indexed by availability time
    data = {col: [getattr(r, col) for r in derivatives_rows] for col in target_cols}
    avail_df = pd.DataFrame(data, index=availability).sort_index()
    avail_df = avail_df[~avail_df.index.duplicated(keep="last")]

    # Reindex to ohlcv timestamps and forward-fill (latest available wins)
    aligned = avail_df.reindex(result.index, method="ffill")
    for col in target_cols:
        result[col] = aligned[col].values
    return result
```

**Verify:** `pytest tests/test_infrastructure/test_derivatives_merger.py -v` (scenario 5.1)
**Common mistake:** The `DerivativesMetrics` dataclass is at `finbar.core.domain.entities.derivatives_metrics` (NOT in the package). Import from there, not from `finbar_strategy_runtime`.

### Step 5.2: Wire the merge into CachedPriceIndicatorJobRunner

**Context:** Backtests consume **pre-computed indicator artifacts** (see
`backtest_strategy_definition.py`: "This use case intentionally does not
fetch prices or calculate indicators"). The indicator computation happens
in `CachedPriceIndicatorJobRunner.run()` (line ~177, where
`self._indicator_calculator.calculate(frame, indicators)` is called). The
merge must happen THERE, before `calculate()`, so the derivatives columns
are present when OHLCV handlers run.

**File:** `finbar/infrastructure/services/indicator_job_runner.py` (modify)

1. Add `derivatives_repository: DerivativesRepository | None = None` to
   `CachedPriceIndicatorJobRunner.__init__()`.
2. In `run()`, after building the frame and before calling
   `self._indicator_calculator.calculate(frame, indicators)`, check if any
   requested indicator is a derivatives metric. If so, load derivatives data
   from the repository for the job's symbol and interval, and call
   `merge_derivatives_asof(frame, derivatives_rows, interval)`.

```python
# In CachedPriceIndicatorJobRunner.run(), before calculate():
_DERIVATIVES_INDICATORS = {
    "funding_rate", "open_interest", "open_interest_delta_1h",
    "open_interest_delta_24h", "cumulative_volume_delta",
    "long_short_ratio", "liquidations_long_1h", "liquidations_short_1h",
    "liquidations_long_24h", "liquidations_short_24h",
}

if self._derivatives_repository and any(i in _DERIVATIVES_INDICATORS for i in indicators):
    deriv_rows = self._derivatives_repository.find(
        symbol=job.symbol,
        start_time=<frame start>,
        end_time=<frame end>,
    )
    frame = merge_derivatives_asof(frame, deriv_rows, interval=job.interval)
```

3. Wire the repository in `finbar/startup/service_factory.py` — add
   `_get_derivatives_repository()` that returns a `SqlCoinGlassRepository(db)`,
   and inject it into the runner factory.

**Verify:** scenario 5.2 (integration test — strategy references `funding_rate`
after `fetch_derivatives` was run; backtest completes and condition evaluates).
**Common mistake:** If the repository is None (derivatives not configured), skip
the merge — the handler will still write an all-NaN column (Invariant #2).

### Step 5.3: Register derivatives metrics in the catalog
**File:** `_metric_registry.py` (modify)

The 11 derivatives entries already exist (from the prior spec). Update them so
their `required_data_classes` reflects the new merge capability. Add a
`requires_derivatives_data: bool = False` flag so `check()` can consult the
repository.

### Step 5.4: CheckMetricCapabilityUseCase + DI wiring

**File:** `finbar/core/application/use_cases/check_metric_capability.py` (new)

```python
"""CheckMetricCapabilityUseCase — can a metric be computed for a symbol?"""

from finbar.core.domain.entities.derivatives_metrics import DerivativesMetrics
from finbar.core.domain.interfaces.derivatives_repository import DerivativesRepository
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog


class CheckMetricCapabilityUseCase:
    """Check metric computability, consulting the DB for derivatives metrics."""

    def __init__(self, repository: DerivativesRepository | None = None):
        self._repository = repository
        self._catalog = UnifiedMetricCatalog()

    def execute(self, name: str, symbol: str = "", data_class: str = "daily_ohlcv"):
        result = self._catalog.check(name, data_class)
        # For derivatives metrics, also check if data is in the DB
        definition = self._catalog.get(name)
        if (self._repository and definition
                and definition.family.value == "derivatives"):
            rows = self._repository.find(symbol=symbol)
            if not rows:
                # Override: data not fetched yet
                return result._replace(
                    computable=False,
                    warnings=("Run fetch_derivatives first to populate this metric.",),
                )
        return result
```

**File:** `finbar/presentation/mcp/tools/_shared.py` + `finbar/startup/service_factory.py`

Add `_make_check_metric_capability_use_case()` to the service factory,
injecting the `SqlCoinGlassRepository`. Then the MCP `check_metric` tool
calls this use case (with the symbol from the tool arguments).

**Verify:** scenario 5.3.

---

## Slice 6 — New Fetchers

### Step 6.1: Probe the CoinGlass liquidation/long-short-ratio response shape

Before writing the parsers, you MUST inspect the actual API response to get
the field names. These endpoints were confirmed to exist (HTTP 401 without a
key) but their response JSON shapes are not documented in the SDK.

**Manual probe (run once with a valid API key):**
```bash
COINGLASS_API_KEY=<your-key> python -c "
import requests, json
h = {'accept': 'application/json', 'CG-API-KEY': '$COINGLASS_API_KEY'}
for ep in ['/api/futures/liquidation/aggregated-history',
           '/api/futures/global-long-short-account-ratio/history']:
    r = requests.get(f'https://open-api-v4.coinglass.com{ep}',
                     params={'symbol':'BTC','interval':'1h','limit':2}, headers=h)
    print(f'=== {ep} ===')
    print(json.dumps(r.json(), indent=2)[:1000])
"
```

Record the field names from the response (e.g. `long_usd`, `short_usd`, or
`longLiqs`, `shortLiqs`). Use those exact names in the parser functions below.

### Step 6.2: CoinGlass fetch_liquidations
**File:** `finbar/infrastructure/services/coinglass_client.py` (modify — add method)

```python
def fetch_liquidations(self, symbol, interval="1h", exchange="Binance", limit=500):
    """Fetch aggregated liquidation history."""
    self._require_key()
    full_symbol = self._get_full_symbol(symbol, exchange) or _to_full_symbol(symbol)
    params = {"exchange_list": exchange, "symbol": full_symbol,
              "interval": interval, "limit": limit}
    raw = self._get("/api/futures/liquidation/aggregated-history", params)
    return _parse_liquidations(raw, symbol, interval)


def _parse_liquidations(raw, symbol, interval):
    # Use the field names from the Step 6.1 probe.
    # Expected shape (verify before coding!):
    #   [{"time": <ms>, "long_usd": ..., "short_usd": ...}, ...]
    of = _opt_float
    return [
        DerivativesMetrics(
            symbol=symbol,
            timestamp=_parse_ts(item),
            interval=interval,
            liquidations_long_1h=of(_first_not_none(item, "long_usd", "longLiqs")),
            liquidations_short_1h=of(_first_not_none(item, "short_usd", "shortLiqs")),
        )
        for item in raw
    ]
```

**Verify:** scenario 6.1 (skipped without API key).

### Step 6.3: CoinGlass fetch_long_short_ratio
**File:** `coinglass_client.py` (modify)

```python
def fetch_long_short_ratio(self, symbol, interval="1h", limit=500):
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    raw = self._get("/api/futures/global-long-short-account-ratio/history", params)
    return _parse_long_short(raw, symbol, interval)


def _parse_long_short(raw, symbol, interval):
    # Use field names from the Step 6.1 probe.
    of = _opt_float
    return [
        DerivativesMetrics(
            symbol=symbol, timestamp=_parse_ts(item), interval=interval,
            long_short_ratio=of(_first_not_none(item, "long_short_ratio", "ratio")),
        )
        for item in raw
    ]
```

**Verify:** scenario 6.2.

### Step 6.4: Hyperliquid fetch_funding_history
**File:** `finbar/infrastructure/services/hyperliquid_fetcher.py` (modify — add method)

```python
def fetch_funding_history(self, symbol, interval="1h", start_date=None, end_date=None):
    """Fetch funding-rate history (free, no API key needed)."""
    info = self._get_info()
    start_ms = int(_to_utc(start_date or ...).timestamp() * 1000)
    end_ms = int(_to_utc(end_date or datetime.now(UTC)).timestamp() * 1000)
    raw = info.funding_history(symbol, start_ms, end_ms)
    return [ DerivativesMetrics(symbol=symbol, timestamp=..., funding_rate=float(r["fundingRate"])) for r in raw ]
```

**Verify:** scenario 6.3.
**Common mistake:** Handle HIP-3 symbols (`flx:TSLA`) — `info.funding_history` takes the plain coin name, not the `dex:COIN` form.

### Step 6.5: Update the fetch_derivatives MCP tool description
**File:** `finbar/presentation/mcp/tools/derivatives.py` (modify)

Mention liquidations + long/short ratio are now fetchable.

---

## Final verification

After all slices:
```bash
# Package tests
cd packages/strategy-runtime && .venv/Scripts/python.exe -m pytest tests/ -q

# Finbar tests
cd ../.. && .venv/Scripts/python.exe -m pytest tests/ -q

# Name-sync invariant (scenario 1.3)
.venv/Scripts/python.exe -m pytest tests/contract/ -k name_sync -v
```

All must pass. Commit per step (or per module within Slices 2/3).
