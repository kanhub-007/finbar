# Implementation Guide — Extended Market Metrics and Data Requirements

## Step 1: Build the exhaustive metric catalog
**Files:**
- `finbar/core/domain/entities/data_class.py`
- `finbar/core/domain/entities/market_metric_definition.py`
- `finbar/core/domain/entities/data_requirement.py`
- `finbar/core/domain/entities/metric_capability_result.py`
- `finbar/core/domain/interfaces/market_metric_catalog.py`
- `finbar/core/application/services/static_market_metric_catalog.py`

The catalog must register **every** metric listed in `03-domain.md` — ~160 entries total across all families. Each entry includes: name, family, required data class, required columns (if OHLCV), min lookback, confidence classification, paper reference, and proxy candidates (when actual metric is unavailable).

Re-catalogue existing Finbar indicators (proxy_parkinson → parkinson_vol, etc.) so the catalog is the single source of truth.

**Verify:** Unit test asserts `catalog.list()` returns ≥ 160 entries and every metric from the intraday proxy doc (Sections 2-13) is present.

**Common mistake:** Omitting metrics that require unavailable data. Every documented metric must be in the catalog, even if `computable=false` for current data.

---

## Step 2: Add data availability checks before any metric calculation
**Files:**
- `finbar/core/domain/interfaces/data_availability_provider.py`
- `finbar/core/application/use_cases/check_market_metric_capabilities.py`

The use case inspects cached bars/artifacts/source metadata and returns `MetricCapabilityResult` per metric, before jobs/backtests. It must:
- block metrics requiring unavailable data classes,
- suggest proxy candidates ranked by correlation to ground truth,
- not silently substitute proxies for actual metrics.

**Verify:** Requesting `cont_kukanov_ofi` against daily OHLCV returns `computable=false` with `missing_data_classes=["level_2_order_book"]` and `proxy_candidates=["bvc_ofi"]`.

**Common mistake:** Silently computing proxies when the user asked for an actual metric. The user must explicitly choose the proxy.

---

## Step 3: Implement all OHLCV proxy calculators (54 metrics)
**Files:**

### Spread proxies
- `finbar/core/domain/services/spread_proxies.py`
  - `corwin_schultz_spread` (OHLC, with overnight-gap adjustment toggle)
  - `roll_spread` (close, zero when cov ≥ 0 with diagnostic)
  - `abdi_ranaldo_spread` (OHLC)
  - `effective_tick_spread` (close, configurable tick sizes)
  - `fong_holden_tran_spread` (OHLC)
  - `chung_zhang_spread` (OHLC)
  - `lot_zero_return_spread` (close, logistic mapping)

### Volatility
- `finbar/core/domain/services/volatility_estimators.py`
  - `close_to_close_vol` (close) — new
  - `parkinson_vol` — re-register existing `proxy_parkinson` function
  - `garman_klass_vol` — re-register existing `proxy_garman_klass`
  - `rogers_satchell_vol` — re-register existing `proxy_rogers_satchell`
  - `yang_zhang_vol` — re-register existing pure function as indicator column
  - `gk_plus_overnight_vol` (OHLC) — new
  - `meilijson_vol` (OHLC) — new
  - `daily_return_skewness` (close, rolling) — new
  - `daily_return_kurtosis` (close, rolling) — new

### Liquidity / impact
- `finbar/core/domain/services/liquidity_proxies.py`
  - `amihud_illiq` (close, volume) — new
  - `amivest_liquidity` (close, volume) — new
  - `florackis_lambda` (close, volume) — new
  - `hasbrouck_daily_lambda` (close, volume) — new
  - `pastor_stambaugh_liquidity` (close, volume, multi-asset) — new
  - `liu_illiq` (volume, threshold) — new
  - `turnover` (volume) — new (requires shares_outstanding input or average-volume proxy)
  - `bao_pan_zhou_cost` (close) — new

### Order flow
- `finbar/core/domain/services/order_flow_proxies.py`
  - `signed_sqrt_volume_ofi` (close, volume) — new
  - `bvc_buy_volume` (close, volume, volatility) — new
  - `bvc_sell_volume` (close, volume, volatility) — new
  - `bvc_ofi` (close, volume, volatility) — new
  - `cumulative_signed_volume_ofi` (close, volume) — new
  - `return_volume_correlation` (close, volume) — new

### Informed trading
- `finbar/core/domain/services/informed_trading_proxies.py`
  - `daily_vpin` (close, volume, volatility) — new
  - `spread_based_pin_proxy` — new (needs CS spread as prerequisite)

### Jump / tail risk
- `finbar/core/domain/services/jump_risk_proxies.py`
  - `jump_gap_proxy` (OHLC) — new
  - `extreme_return_flag` (close, n_sigma configurable) — new
  - `cc_rs_jump_proxy` (OHLC) — new
  - `overnight_gap_proxy` (open, previous close) — new

### Intraday seasonality
- `finbar/core/domain/services/intraday_seasonality_proxies.py`
  - `overnight_intraday_decomp` (OHLC) — new
  - `parametric_u_shape` (volume) — new
  - `first_last_hour_vol_fraction` — new (requires provider fields; diagnostic if unavailable)

### Order arrival
- `finbar/core/domain/services/order_arrival_proxies.py`
  - `volume_to_trade_count_proxy` — new
  - `trade_count_daily` — new (diagnostic if provider field missing)

### Resiliency
- `finbar/core/domain/services/resiliency_proxies.py`
  - `resiliency_autocorr` (close) — new
  - `resiliency_spread_to_impact` (OHLCV) — new
  - `inverse_amihud_resiliency` (close, volume) — new

### Information share
- `finbar/core/domain/services/information_share_proxies.py`
  - `cross_price_leadership` — new (requires multi-asset bars)
  - `volume_weighted_is` — new
  - `opening_price_leadership` — new
  - `daily_cross_correlation` — new (rolling correlation of close-to-close returns between two assets)
  - `daily_beta_ols` — new (rolling OLS regression of asset returns on benchmark returns)

### Infrastructure calculator (wires everything together)
- `finbar/infrastructure/services/pandas_market_metric_calculator.py`
  Composite calculator that dispatches to family-specific strategies via the catalog.

**Verify:** Deterministic fixture tests for every metric. Each metric must have at least one black-box test with known inputs/outputs.

**Common mistake:** Returning zeros for invalid prices/volumes. Prefer NaN + structured diagnostic.

---

## Step 4: Implement all price-action and trading-theory calculators (50 metrics)
**Files:**

### Fibonacci
- `finbar/core/domain/services/fibonacci_levels.py`
  - Fib retracement from last completed swing high → swing low, or swing low → swing high.
  - All 5 retracement levels: `fib_236_retrace`, `fib_382_retrace`, `fib_500_retrace`, `fib_618_retrace`, `fib_786_retrace`.
  - All 4 extension levels: `fib_1272_extension`, `fib_1618_extension`, `fib_2000_extension`, `fib_2618_extension`.
  - `fib_confluence_score`: 0-4 score counting how many Fib levels from different swing pairs cluster within 1-2 ticks.
  - Swing detection window configurable; defaults to 5 bars.
  - Levels emit only after both swing legs are fully closed (no look-ahead).

### Supply/Demand zones
- `finbar/core/domain/services/supply_demand_zones.py`
  - RBR/DBR demand zones; DBD/RBD supply zones.
  - Zone scoring: departure strength, time at zone, volume at departure, times tested, timeframe, confluence (0-6).
  - `zone_failure_bullish`: demand zone broken below with strong volume → flipped to supply (doc section 17.5).
  - `zone_failure_bearish`: supply zone broken above with strong volume → flipped to demand.

### SMC approximations
- `finbar/core/domain/services/smc_price_action.py`
  - FVG from 3-candle patterns (gap between candle-1 high and candle-3 low).
  - Order blocks from impulse analysis.
  - Breaker blocks: failed OB that flips polarity (doc section 18.1).
  - Liquidity sweeps = break of prior swing + immediate reversal.
  - BOS = break in trend direction; CHoCH = break against trend.
  - Premium/discount = upper/lower half of swing range.

### VSA signals
- `finbar/core/domain/services/vsa_signals.py`
  - `no_demand`, `no_supply`: small bar + low relative volume.
  - `stopping_volume`: high volume + narrow spread near range bottom.
  - `climax_volume`: extreme volume + wide spread (vs. rolling average).
  - `effort_to_rise`, `effort_to_fall`: wide bar + high volume + close near middle.
  - `effort_result_divergence`: composite of above.
  - `bag_holding`: high-vol up bar after decline, followed by down bar.
  - `shakeout`: break below support + high volume + immediate rally.
  - `test`: low-vol retest of prior stopping-volume area.
  - All thresholds configurable (volume multiplier, spread percentiles).

### Bill Williams indicators
- `finbar/core/domain/services/bill_williams_indicators.py`
  - Williams fractals: buy fractal = highest bar in 5-bar window with 2 bars on each side.
  - Alligator: 3 SMMA lines at periods 5/8/13 shifted forward.
  - `alligator_status`: categorical sleeping/waking/eating from line convergence.
  - AO = SMA(median, 5) − SMA(median, 34).
  - AC = AO − SMA(AO, 5).
  - `zone_signal`: Green (AO+ AC+), Red (AO− AC−), Gray (mixed) from AO+AC combination (doc section 20.4).

### Fractal / Hurst
- `finbar/core/domain/services/hurst_regime.py`
  - R/S analysis with configurable lookback.
  - `hurst_exponent`: H > 0.55 trending, H < 0.45 mean-reverting, else random walk.
  - `fractal_regime`: categorical output from Hurst.

### Dow Theory / trend structure
- `finbar/core/domain/services/trend_structure.py`
  - Generalize existing `swing_high_20`/`swing_low_20` to configurable window.
  - `hh_hl_pattern`, `lh_ll_pattern`: boolean flags from swing sequence.
  - `volume_trend_confirmation`: volume > average on trend-direction bars.
  - `trend_phase`: Accumulation / Public Participation (Markup) / Distribution based on volume structure (doc section 11.2).

### Market Profile day types
- Add to existing `finbar/core/domain/services/` or `profile_shape.py`:
  - `day_type_classification`: Normal / NormalVariation / Trend / DoubleDistribution / Neutral / NonTrend from IB width, profile shape, and follow-through (doc section 13.1).

### Adaptive Markets regime
- `finbar/core/domain/services/market_regime.py`:
  - `market_regime`: TRENDING_BULL / TRENDING_BEAR / RANGE_BOUND / CRISIS.
  - Composite from: 200-MA position, ADX(14), Hurst (optional), VIX level (optional).
  - When VIX unavailable: use `yang_zhang_vol` percentile as crisis proxy.
  - Defaults to RANGE_BOUND when insufficient data.

### Elliott Wave (catalogued, not implemented)
- Catalog entry only — no computation in this slice.
- Future implementation requires: swing detection, 3-rule validation engine, corrective pattern classifier.
- Metrics reserved in catalog: `elliott_wave_count`, `elliott_wave_phase`, `elliott_zigzag_correction`, `elliott_flat_correction`, `elliott_triangle_correction`.

### Existing services — do NOT reimplement
- `wyckoff_phase.py` / `wyckoff_wrappers.py` — existing, add to catalog as-is.
- `profile_shape.py` / `profile_shape_wrappers.py` — existing, add to catalog.
- `coil_detector.py` — existing, add to catalog.

**Verify:** Every metric has a test proving no look-ahead bias (patterns emit only after required future bars close). Every metric is labelled `confidence: "approximation"`.

**Common mistake:** Detecting a swing/fractal at bar T using bars T+1, T+2. Patterns must emit at the last bar of the detection window, never before.

---

## Step 5: Integrate with existing indicator and strategy workflows
**Files:**
- `finbar/core/application/use_cases/apply_market_metrics.py` (new use case)
- `finbar/presentation/mcp/tools/market_metrics.py` (new MCP tool)
- Existing `apply_indicators` / `compute_indicators` unchanged

Add a new market metrics use case and MCP tool rather than overloading the existing `compute_indicators` pipeline. The existing indicator pipeline continues to work unchanged. The metrics use case:
1. checks catalog capabilities for each requested metric against available data,
2. computes all OHLCV-computable metrics,
3. returns skipped metrics with diagnostics and proxy suggestions,
4. persists applied metric names in artifact metadata.

**Verify:** MCP/API returns structured diagnostics (applied, skipped, unavailable) and persists metric names in artifacts.

**Common mistake:** Mixing metric diagnostics into raw bar output as unlabeled columns.

---

## Step 6: Register existing-but-unregistered indicators as catalog entries
**Files:**
- `finbar/core/domain/services/proxy_indicator.py` — functions remain, catalog references them.
- `finbar/core/application/services/strategy_indicator_catalog.py` — add cross-reference to `MarketMetricCatalog` for strategy operand validation.

Existing indicators that are already in the indicator catalog (`atr`, `rsi_14`, `vp_poc`, etc.) stay in `StrategyIndicatorCatalog` and are also referenced by `MarketMetricCatalog` for completeness. No duplication of computation logic.

**Verify:** Strategy referencing `corwin_schultz_spread` in its conditions validates correctly when OHLCV data is available. Strategy referencing `effective_spread_taq` is rejected with required `trades_and_quotes`.

**Common mistake:** Duplicating the indicator catalog. The metric catalog is a superset — it includes all strategy indicators PLUS the new metrics. Indicators that already have `@register` handlers keep them.

---

## Step 7: Implement dual-path resolution for intraday-vs-proxy metrics
**Files:**
- `finbar/core/domain/entities/metric_resolution_path.py`
- `finbar/core/domain/interfaces/market_metric_catalog.py` — add `resolve_best()`
- `finbar/core/application/services/static_market_metric_catalog.py` — implement auto-selection

For every conceptual metric that has both an actual intraday method and daily proxy estimators, the catalog must define ordered resolution paths:

```python
# Example catalog entry for the "volatility" conceptual metric:
MetricDefinition(
    name="volatility",
    family="volatility",
    resolution_paths=[
        MetricResolutionPath(
            metric_name="realized_vol_5m",
            required_data_class="intraday_ohlcv",
            interval_min="5min",
            confidence="actual",
            priority=1,
        ),
        MetricResolutionPath(
            metric_name="realized_vol_1h",
            required_data_class="intraday_ohlcv",
            interval_min="1h",
            confidence="approximation",
            priority=2,
        ),
        MetricResolutionPath(
            metric_name="yang_zhang_vol",
            required_data_class="daily_ohlcv",
            confidence="proxy",
            priority=3,
        ),
    ],
)
```

`resolve_best(concept, availability, force_proxy=False)` walks the paths in priority order and returns the first path whose data requirements are satisfied. When `force_proxy=True`, it skips all `actual` and `approximation` paths.

**Verify:** `resolve_best("volatility", intraday_5min_availability)` returns `realized_vol_5m` with `confidence="actual"`. `resolve_best("volatility", daily_only_availability)` returns `yang_zhang_vol` with `confidence="proxy"`.

**Common mistake:** Returning raw Python enums in MCP responses. Serialize to strings.

---

## Step 8: Publish catalog metadata for MCP/API consumers
**Files:**
- `finbar/presentation/mcp/tools/market_metrics.py`

Expose:
- `list_market_metrics(family=None)` — list all metrics with data requirements, resolution paths, and confidence.
- `check_market_metric_capabilities(metrics, symbol, source, interval)` — per-metric computability with auto-selected best path.

**Verify:** MCP response includes `selected_metric`, `confidence`, `available_paths`, `required_data_class`, `missing_data_classes`, `proxy_candidates` for every metric.

**Common mistake:** Returning raw Python enums or objects in MCP responses. Serialize to JSON-safe dicts.
