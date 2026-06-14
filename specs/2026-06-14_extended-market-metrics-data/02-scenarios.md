# Scenarios — Extended Market Metrics and Data Requirements

Scenarios use Classical-school, black-box tests. Metric calculators should be real pure services; repositories/providers are fakes at boundaries.

---

### Scenario: Metric catalog reports support and required data class
**Priority:** Must  
**Slice:** 1

**Gherkin:**
  Given a requested metric name and available dataset metadata
  When Finbar resolves metric capabilities
  Then it reports whether the metric is supported, which data class is required, current availability, proxy candidates, and confidence classification

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| metric_name | string | `corwin_schultz_spread` | Required |
| available_data_class | enum | `daily_ohlcv` | Known data class |
| interval | string | `1d` | Supported interval |
| symbol | string | `AAPL` | Required |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| every documented metric is known by the catalog | Inspect `list()` output |
| OHLCV proxy returns `computable=true` and `confidence=proxy` | Inspect capability result |
| tick/quote/L2-only metric returns `computable=false` with required data class | Inspect diagnostics |
| output includes required columns, minimum lookback, and papers/sources | Inspect capability result |
| unknown names fail clearly with validation error | Inspect validation error |
| proxy candidates are suggested when actual metric is unavailable | Inspect result.proxy_candidates |

**Verify (Classical school, black-box):**
```python
catalog = MarketMetricCatalog()
result = catalog.check("corwin_schultz_spread", available_data_class="daily_ohlcv")

assert result.supported is True
assert result.computable is True
assert result.confidence == "proxy"
assert result.required_data_class == "daily_ohlcv"

l2 = catalog.check("order_book_depth_profile", available_data_class="daily_ohlcv")
assert l2.computable is False
assert "level_2_order_book" in l2.missing_data_classes
assert len(l2.proxy_candidates) > 0
```

**Also test:**
- Every metric from the intraday proxy doc is present in `list()`.
- `effective_spread_taq` requires `trades_and_quotes`.
- `cont_kukanov_ofi` requires Level 2 / order-book events.
- `hasbrouck_information_share` requires multi-venue tick data.
- `amihud_illiq` is computable from `daily_ohlcv`.
- Catalog response is JSON-serializable for MCP/API.
- Unknown metric name returns clear "unknown metric" diagnostic, separate from "known but unavailable."

---

### Scenario: All OHLCV-computable market microstructure proxies are available
**Priority:** Must  
**Slice:** 2

**Gherkin:**
  Given daily or intraday OHLCV bars with sufficient lookback
  When Finbar computes any supported OHLCV microstructure proxy
  Then every metric returns deterministic output, with NaN for insufficient-data rows and diagnostics for invalid input

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| bars | DataFrame/list[dict] | OHLCV bars | Required columns: open/high/low/close/volume |
| metrics | list[string] | any from the full proxy catalog | Must be OHLCV-computable |
| lookback | int | varies per metric | Positive, documented per metric |

**Expected output / state change:**

**Bid-ask spread proxies (7 metrics)** — all from Section 2 of proxy doc:

| Metric | Required columns | Paper | Status |
|--------|-----------------|-------|--------|
| `corwin_schultz_spread` | OHLC | Corwin-Schultz (2012) | New |
| `roll_spread` | close | Roll (1984) | New |
| `abdi_ranaldo_spread` | OHLC | Abdi-Ranaldo (2017) | New |
| `effective_tick_spread` | close | Holden (2009) | New |
| `fong_holden_tran_spread` | OHLC | FHT (2017) | New |
| `chung_zhang_spread` | OHLC | Chung-Zhang (2014) | New |
| `lot_zero_return_spread` | close | LOT (1999) | New |

**Volatility estimators (8 metrics)** — Section 3:

| Metric | Required columns | Paper | Status |
|--------|-----------------|-------|--------|
| `close_to_close_vol` | close | Naive | New (catalogue existing logic) |
| `parkinson_vol` | HL | Parkinson (1980) | **Exists** as `proxy_parkinson` — register as catalogue entry |
| `garman_klass_vol` | OHLC | GK (1980) | **Exists** as `proxy_garman_klass` — register |
| `rogers_satchell_vol` | OHLC | RS (1991) | **Exists** as `proxy_rogers_satchell` — register |
| `yang_zhang_vol` | OHLC | YZ (2000) | **Exists** as pure function — register as requestable column |
| `gk_plus_overnight_vol` | OHLC | Combined | New |
| `meilijson_vol` | OHLC | Meilijson (2009) | New |
| `daily_return_skewness` | close | — | New |
| `daily_return_kurtosis` | close | — | New |

**Liquidity / price-impact proxies (8 metrics)** — Sections 4, 8:

| Metric | Required columns | Paper | Status |
|--------|-----------------|-------|--------|
| `amihud_illiq` | close, volume | Amihud (2002) | New |
| `amivest_liquidity` | close, volume | Amivest | New (inverse of Amihud) |
| `florackis_lambda` | close, volume | FGK (2011) | New |
| `hasbrouck_daily_lambda` | close, volume | Hasbrouck (2009) | New |
| `pastor_stambaugh_liquidity` | close, volume | PS (2003) | New (multi-asset) |
| `liu_illiq` | volume | Liu (2006) | New |
| `turnover` | volume, shares_outstanding | — | New |
| `bao_pan_zhou_cost` | close | BPZ (2011) | New |

**Order-flow proxies (5 metrics)** — Section 5:

| Metric | Required columns | Paper | Status |
|--------|-----------------|-------|--------|
| `signed_sqrt_volume_ofi` | close, volume | Chordia-Subrahmanyam (2004) | New |
| `bvc_buy_volume` | close, volume, volatility | ELO (2012) | New |
| `bvc_sell_volume` | close, volume, volatility | ELO (2012) | New |
| `bvc_ofi` | close, volume, volatility | ELO (2012) | New |
| `cumulative_signed_volume_ofi` | close, volume | — | New |
| `return_volume_correlation` | close, volume | — | New |

**Informed-trading proxies (2 metrics)** — Section 6:

| Metric | Required columns | Paper | Status |
|--------|-----------------|-------|--------|
| `daily_vpin` | close, volume, volatility | ELO (2012) | New |
| `spread_based_pin_proxy` | Corwin-Schultz + reversal proxy | Derived | New (needs CS spread first) |

**Jump / tail-risk proxies (4 metrics)** — Section 9:

| Metric | Required columns | Paper | Status |
|--------|-----------------|-------|--------|
| `jump_gap_proxy` | OHLC | Derived | New |
| `extreme_return_flag` | close | 3-sigma rule | New |
| `cc_rs_jump_proxy` | OHLC | Derived | New |
| `overnight_gap_proxy` | open, prev-close | Derived | New |

**Intraday-seasonality proxies (3 metrics)** — Section 10:

| Metric | Required columns | Paper | Status |
|--------|-----------------|-------|--------|
| `overnight_intraday_decomp` | OHLC | — | New |
| `parametric_u_shape` | volume | Parametric | New |
| `first_last_hour_vol_fraction` | opening/closing volume fields | — | New (depends on provider) |

**Order-arrival proxies (2 metrics)** — Section 11:

| Metric | Required columns | Paper | Status |
|--------|-----------------|-------|--------|
| `volume_to_trade_count_proxy` | volume, avg_trade_size | — | New |
| `trade_count_daily` | trade_count field | — | New (depends on provider) |

**Resiliency proxies (3 metrics)** — Section 12:

| Metric | Required columns | Paper | Status |
|--------|-----------------|-------|--------|
| `resiliency_autocorr` | close | — | New |
| `resiliency_spread_to_impact` | OHLCV | Derived | New |
| `inverse_amihud_resiliency` | close, volume | Derived | New |

**Information-share proxies (3 metrics)** — Section 13:

| Metric | Required columns | Paper | Status |
|--------|-----------------|-------|--------|
| `cross_price_leadership` | close (multi-asset) | — | New |
| `volume_weighted_is` | volume (multi-asset) | — | New |
| `opening_price_leadership` | open (multi-asset) | — | New |

**Verify (Classical school, black-box):**
```python
calculator = MarketMetricCalculator(catalog=MarketMetricCatalog())
result = calculator.calculate(
    bars,
    ["corwin_schultz_spread", "amihud_illiq", "bvc_ofi", "yang_zhang_vol",
     "daily_vpin", "overnight_intraday_decomp", "resiliency_spread_to_impact"]
)

for col in ["corwin_schultz_spread", "amihud_illiq", "bvc_ofi",
            "yang_zhang_vol", "daily_vpin", "overnight_vol",
            "intraday_vol", "resiliency_spread_to_impact"]:
    assert col in result.columns

assert len(result) == len(bars)
assert result["amihud_illiq"].dropna().ge(0).all()
```

**Also test:**
- Zero/negative volume → NaN + warning, not crash.
- Non-positive prices → diagnostic NaN per row.
- Overnight-gap adjustment for Corwin-Schultz is enabled by default, configurable.
- BVC uses YZ volatility; rejects missing volatility with diagnostic.
- Every metric has a deterministic fixture test.
- Existing proxy columns (`proxy_parkinson`, `proxy_garman_klass`, `proxy_rogers_satchell`, `proxy_vwap`) continue to work unchanged.

---

### Scenario: All OHLCV-computable price-action and trading-theory metrics are available
**Priority:** Must  
**Slice:** 3

**Gherkin:**
  Given OHLCV bars with sufficient lookback
  When Finbar computes any supported price-action metric
  Then every metric returns deterministic output, labelled as OHLCV approximation, with no look-ahead bias

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| bars | list[dict] | OHLCV bars | Enough lookback for swings/fractals |
| metrics | list[string] | any from the price-action catalog | Must be OHLCV-computable |
| swing_window | int | `5` | Configurable, positive |

**Expected output / state change:**

**Fibonacci levels (9 metrics)** — covering all levels from docs:

| Metric | Description |
|--------|-------------|
| `fib_236_retrace` | 23.6% retracement — shallow pullback in strong trends |
| `fib_382_retrace` | 38.2% retracement — most common in healthy trends |
| `fib_500_retrace` | 50% retracement — widely watched half-retracement |
| `fib_618_retrace` | 61.8% retracement — the golden ratio, key level |
| `fib_786_retrace` | 78.6% retracement — last chance for trend continuation |
| `fib_1272_extension` | 127.2% extension — conservative target |
| `fib_1618_extension` | 161.8% extension — standard target, most commonly hit |
| `fib_2000_extension` | 200% extension — strong trend target |
| `fib_2618_extension` | 261.8% extension — extreme trend target |
| `fib_confluence_score` | 0-4 score: number of Fib levels clustering within a tick zone |

| Metric | Required columns | Notes |
|--------|-----------------|-------|
| `fib_382_retrace` | OHLC + swing detection | 38.2% retracement level |
| `fib_500_retrace` | OHLC + swing detection | 50% retracement level |
| `fib_618_retrace` | OHLC + swing detection | 61.8% golden ratio retracement |
| `fib_1618_extension` | OHLC + swing detection | 161.8% extension target |

**Supply/Demand zones (8 metrics)** — from doc sections 17.1-17.5:

| Metric | Required columns | Notes |
|--------|-----------------|-------|
| `demand_zone_low` | OHLC | Rally-base-rally or drop-base-rally zone bottom |
| `demand_zone_high` | OHLC | Zone top |
| `demand_zone_score` | OHLCV | 0-6 quality score (departure strength, time, volume, touches, TF, confluence) |
| `supply_zone_low` | OHLC | Zone bottom |
| `supply_zone_high` | OHLC | Zone top |
| `supply_zone_score` | OHLCV | 0-6 quality score |
| `zone_failure_bullish` | OHLCV | Demand zone broken below + strong volume → flipped to supply |
| `zone_failure_bearish` | OHLCV | Supply zone broken above + strong volume → flipped to demand |

**SMC / Smart Money Concepts approximations (11 metrics)** — from doc sections 18.1-18.6:

| Metric | Required columns | Notes |
|--------|-----------------|-------|
| `bullish_fvg` | OHLC | Three-candle bull fair value gap (candle-1 high < candle-3 low) |
| `bearish_fvg` | OHLC | Three-candle bear fair value gap (candle-1 low > candle-3 high) |
| `bullish_order_block` | OHLC | Last bearish candle before strong bullish impulse |
| `bearish_order_block` | OHLC | Last bullish candle before strong bearish impulse |
| `breaker_block_bullish` | OHLC | Failed bearish OB that flips to support |
| `breaker_block_bearish` | OHLC | Failed bullish OB that flips to resistance |
| `liquidity_sweep_high` | OHLC | Break above prior high then immediate reversal |
| `liquidity_sweep_low` | OHLC | Break below prior low then immediate reversal |
| `bos` | OHLC | Break of structure — breaks a swing point in trend direction (continuation) |
| `choch` | OHLC | Change of character — breaks a swing point against trend (reversal) |
| `premium_discount_zone` | OHLC | Upper/lower half of swing range classification |

**VSA / Volume Spread Analysis (10 metrics):**

| Metric | Required columns | Notes |
|--------|-----------------|-------|
| `no_demand` | OHLCV | Small up bar on low volume |
| `no_supply` | OHLCV | Small down bar on low volume |
| `stopping_volume` | OHLCV | High volume + narrow spread at lows |
| `climax_volume` | OHLCV | Extreme volume + wide spread |
| `effort_to_rise` | OHLCV | Wide up bar on high volume, closes middle |
| `effort_to_fall` | OHLCV | Wide down bar on high volume, closes middle |
| `effort_result_divergence` | OHLCV | Composite: high effort + small result |
| `bag_holding` | OHLCV | High-vol up bar after decline, next bar down |
| `shakeout` | OHLCV | Drop below support on high volume then rally |
| `test` | OHLCV | Low-vol retest of stopping volume / support area |

**Bill Williams / Chaos Theory (9 metrics)** — from doc sections 20.1-20.5:

| Metric | Required columns | Notes |
|--------|-----------------|-------|
| `williams_fractal_high` | OHLC | Buy fractal: highest of 5-bar window (2 bars each side) |
| `williams_fractal_low` | OHLC | Sell fractal: lowest of 5-bar window |
| `alligator_jaw` | OHLC | SMMA(median, 13) shifted +8 — slowest line, stop placement |
| `alligator_teeth` | OHLC | SMMA(median, 8) shifted +5 — middle line, exit signal |
| `alligator_lips` | OHLC | SMMA(median, 5) shifted +3 — fastest line |
| `alligator_status` | OHLC | categorical: sleeping / waking / eating based on line spread |
| `awesome_oscillator` | OHLC | SMA(median, 5) − SMA(median, 34) — raw momentum |
| `accelerator_oscillator` | OHLC | AO − SMA(AO, 5) — momentum acceleration |
| `zone_signal` | OHLC | Green (AO+ AC+), Red (AO- AC-), Gray (mixed) — from AO+AC combination |

**Fractal / Hurst (2 metrics)** — from doc section 19.3:

| Metric | Required columns | Notes |
|--------|-----------------|-------|
| `hurst_exponent` | close | R/S analysis, min 100 bars recommended; H>0.55 trending, H<0.45 mean-reverting, near 0.5 random |
| `fractal_regime` | close | categorical: TRENDING / RANDOM / MEAN_REVERTING from rolling Hurst |

**Market Profile day types (1 metric)** — from doc section 13.1:

| Metric | Required columns | Notes |
|--------|-----------------|-------|
| `day_type_classification` | OHLC + IB + profile_shape | Normal / NormalVariation / Trend / DoubleDistribution / Neutral / NonTrend based on IB width, profile shape, and follow-through |

**Adaptive Markets regime (1 metric)** — from doc sections 9.1-9.2 and 21.1:

| Metric | Required columns | Notes |
|--------|-----------------|-------|
| `market_regime` | OHLCV + external (VIX optional) | TRENDING_BULL / TRENDING_BEAR / RANGE_BOUND / CRISIS; composite from 200-MA, ADX, VIX (or VIX proxy), Hurst |

**Elliott Wave (catalogued, not implemented)** — from doc section 15:

Wave counting with 3 inviolable rules (Wave 2 never >100% of Wave 1, Wave 3 never shortest, Wave 4 never enters Wave 1 territory) is a complex pattern recognition problem. The spec catalogues it as an aspirational metric requiring a dedicated wave-detection engine. No OHLCV-computable columns are defined in this slice.

| Metric | Required data | Status |
|--------|---------------|--------|
| `elliott_wave_count` | OHLC + swing detection + rule engine | Future candidate — catalogued, not implemented |
| `elliott_wave_phase` | same | Future candidate |
| `elliott_zigzag_correction` | same | Future candidate |
| `elliott_flat_correction` | same | Future candidate |
| `elliott_triangle_correction` | same | Future candidate |

**Dow Theory trends (6 metrics):** (enhance existing trend indicators, docs sections 11.1-11.4)

| Metric | Required columns | Notes |
|--------|-----------------|-------|
| `swing_high_N` | OHLC | Generalize existing `swing_high_20` to configurable `N` |
| `swing_low_N` | OHLC | Generalize existing `swing_low_20` to configurable `N` |
| `hh_hl_pattern` | OHLC + swings | Uptrend: higher highs + higher lows confirmed |
| `lh_ll_pattern` | OHLC + swings | Downtrend: lower highs + lower lows confirmed |
| `volume_trend_confirmation` | OHLCV | Volume > average on trend-direction bars; volume < average on counter-trend bars |
| `trend_phase` | OHLCV | Accumulation / Public Participation (Markup) / Distribution based on volume structure |

**Verify (Classical school, black-box):**
```python
result = calculator.calculate(bars, [
    "fib_618_retrace", "fib_1618_extension", "awesome_oscillator",
    "bullish_fvg", "no_demand", "hurst_exponent",
    "demand_zone_score", "zone_failure_bullish",
    "breaker_block_bullish", "market_regime",
    "day_type_classification", "alligator_status"
])

for col in ["fib_618_retrace", "fib_1618_extension", "awesome_oscillator",
            "bullish_fvg", "no_demand", "hurst_exponent",
            "demand_zone_score", "zone_failure_bullish",
            "breaker_block_bullish", "market_regime",
            "day_type_classification", "alligator_status"]:
    assert col in result.columns
assert len(result) == len(bars)
```

**Also test:**
- All 9 Fibonacci levels emit correctly from last completed swing.
- Fib levels do not use future bars; both swing legs must be fully closed.
- `fib_confluence_score` increases when multiple Fib levels cluster within 1-2 ticks.
- Zone failure signals emit only after close beyond zone + volume confirmation.
- Breaker blocks detect failed OB with polarity flip.
- `day_type_classification` uses only IB data from first hour-equivalent bars.
- `market_regime` defaults to RANGE_BOUND when VIX/Hurst data unavailable.
- `alligator_status` transitions sleeping→waking→eating based on line convergence.
- `zone_signal` recomputed from AO+AC each bar; Green/Red/Gray categorical.
- FVG uses only completed three-candle patterns, never partial.
- VSA thresholds are configurable via parameters.
- Williams fractals lag 2 bars behind current bar.
- Hurst returns NaN until `min(100, len(bars))` bars available.
- All price-action metrics labelled `confidence: "approximation"` in capabilities.
- Elliott Wave metrics are in the catalog with status `unimplemented`, not silently absent.
- Existing Wyckoff phase and profile shape indicators coexist unchanged.

---

### Scenario: Intraday-bar metrics require intraday bars; daily data rejected with proxy suggestions
**Priority:** Must  
**Slice:** 3

**Gherkin:**
  Given a metric that requires intraday bars or finer data
  When only daily OHLCV is available
  Then Finbar reports the metric as not computable and suggests daily proxy alternatives

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| metric_name | string | `realized_vol_5m` | Requires intraday bars |
| available_interval | string | `1d` | Daily only |
| proxy_allowed | bool | true | If a proxy exists |

**Expected output / state change:**

| Actual metric | Required data | OHLCV proxy candidates |
|---------------|---------------|----------------------|
| `realized_vol_5m` | intraday 5-min bars | `yang_zhang_vol`, `parkinson_vol` |
| `realized_vol_15m` | intraday 15-min bars | `yang_zhang_vol`, `parkinson_vol` |
| `realized_vol_1h` | intraday 1h bars | `yang_zhang_vol`, `garman_klass_vol` |
| `bipower_variation` | intraday returns | `cc_rs_jump_proxy` only as crude proxy |
| `realized_skewness` | intraday returns | `daily_return_skewness` |
| `realized_kurtosis` | intraday returns | `daily_return_kurtosis` |
| `intraday_volume_curve` | intraday bars | `parametric_u_shape` with published defaults only |
| `order_arrival_rate` | tick trades | `volume_to_trade_count_proxy` if avg trade size is known |
| `market_profile_tpo` | intraday bars, ideally 30-min | existing OHLCV TPO approximation only if interval < 1d |
| `trade_count_daily` | trade_count provider field | `volume_to_trade_count_proxy` with estimated avg trade size |

**Verify (Classical school, black-box):**
```python
result = catalog.check("realized_vol_5m", available_data_class="daily_ohlcv")

assert result.computable is False
assert "intraday_ohlcv" in result.missing_data_classes
assert "yang_zhang_vol" in result.proxy_candidates
assert result.confidence == "unavailable"

# With actual intraday data:
result_5m = catalog.check("realized_vol_5m", available_data_class="intraday_ohlcv", interval="5min")
assert result_5m.computable is True
assert result_5m.confidence == "actual"
```

**Also test:**
- 1h bars compute coarse realized volatility with confidence `approximation`.
- Daily bars never silently claim actual realized volatility.
- Proxy suggestion list is ranked by correlation with ground truth.

---

### Scenario: Actual intraday metrics are computed when intraday data is available; proxies when only daily data is available
**Priority:** Must  
**Slice:** 3

**Gherkin:**
  Given a metric concept that has both an actual intraday method and daily proxy estimators
  When intraday bars are available
  Then Finbar computes the actual metric with confidence `actual`; when only daily bars are available, Finbar computes the best proxy with confidence `proxy`

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| metric_concept | string | `volatility`, `spread`, `volume_profile` | Conceptual metric family |
| available_data_class | enum | `intraday_ohlcv` or `daily_ohlcv` | Determines computation path |
| interval | string | `5min` or `1d` | Determines resolution |

**Expected output / state change:**

For every metric concept that has both actual and proxy paths, the catalog must define a preferred resolution order:

| Conceptual metric | Intraday data available → compute | Daily only → compute |
|------------------|-----------------------------------|---------------------|
| Volatility | `realized_vol` (5-min or coarser per interval) | `yang_zhang_vol` |
| Spread | Not computable from OHLCV alone (needs trades+quotes) | `corwin_schultz_spread` |
| Volume Profile | Full Volume Profile from intraday bars | Composite triangle/KDE proxy VP |
| Market Profile | TPO-based POC/VAH/VAL from 30-min bars | Proxy MP from daily bars (wide) |
| Order flow imbalance | Not computable from OHLCV (needs trades or L2) | `bvc_ofi` |
| Price impact | Not computable from OHLCV (needs signed trades) | `amihud_illiq` |
| PIN / informed trading | Not computable from OHLCV (needs classified trades) | `daily_vpin` |
| Jump detection | `bipower_variation` from intraday returns | `cc_rs_jump_proxy` |
| Intraday seasonality | Empirical volume curve from intraday bars | `parametric_u_shape` |
| Order arrival rate | Trade count from tick data | `volume_to_trade_count_proxy` |
| Resiliency | Depth recovery from L2 snapshots | `resiliency_spread_to_impact` |
| Information share | Hasbrouck IS from multi-venue tick | `cross_price_leadership` |

**Dual-path design rules:**
1. The catalog entry for a conceptual metric lists all computation paths ordered by preference.
2. `MarketMetricCalculator` auto-selects the highest-confidence path for which data is available.
3. Users may override: `force_proxy=true` to use a proxy even when intraday data is available.
4. When neither path is available, the metric is skipped with `computable=false`.

**Verify (Classical school, black-box):**
```python
# Intraday data available:
result_5m = catalog.resolve_best("volatility", available_data_class="intraday_ohlcv", interval="5min")
assert result_5m.selected_metric == "realized_vol_5m"
assert result_5m.confidence == "actual"

# Daily data only:
result_daily = catalog.resolve_best("volatility", available_data_class="daily_ohlcv", interval="1d")
assert result_daily.selected_metric == "yang_zhang_vol"
assert result_daily.confidence == "proxy"

# Force proxy override:
result_forced = catalog.resolve_best("volatility", available_data_class="intraday_ohlcv", force_proxy=True)
assert result_forced.selected_metric == "yang_zhang_vol"
```

**Also test:**
- Every conceptual metric in the table above has both paths defined.
- Auto-selection never silently promotes a proxy to `actual`.
- `confidence` field in output always reflects which path was used.
- MCP capability response includes the `selected_path` and available alternatives.

---

### Scenario: Tick, quote, and Level 2 metrics are catalogued but unavailable without required data
**Priority:** Must  
**Slice:** 1

**Gherkin:**
  Given a strategy or user requests a true order-flow or quote/order-book metric
  When Finbar has only OHLCV bars
  Then Finbar reports the exact data class and provider required without silently substituting

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| metric_name | string | `effective_spread_taq` | Known metric |
| available_data_class | enum | `daily_ohlcv` | Insufficient |
| requested_context | enum | strategy_validation / indicator_job | Must fail before backtest |

**Expected output / state change:**

Every metric from the proxy doc that requires non-OHLCV data must be in the catalog:

| Metric | Required data class |
|--------|---------------------|
| `effective_spread_taq` | `trades_and_quotes` |
| `quoted_spread` | `quotes` (Level 1) |
| `realized_spread_taq` | `trades_and_quotes` |
| `lee_ready_classification` | `trades_and_quotes` |
| `kyle_lambda` | `trades_and_quotes` |
| `hasbrouck_var_impact` | `trades_and_quotes` |
| `almgren_chriss_impact` | execution records |
| `cont_kukanov_ofi` | `level_2_order_book` |
| `trade_classified_ofi` | `trades_and_quotes` |
| `noi_from_lob_events` | `order_book_events` |
| `order_book_depth_profile` | `level_2_order_book` |
| `order_book_shape` | `level_2_order_book` |
| `iceberg_detection` | `order_book_events` |
| `spoofing_detection` | `order_book_events` |
| `absorption_detection` | `order_book_events` + `trades_and_quotes` |
| `true_pin_easley` | `trades_and_quotes` (classified buy/sell counts) |
| `intraday_vpin` | volume-bucketed tick trades |
| `depth_recovery_time` | `level_2_order_book` |
| `price_reversion_speed` | `trades_and_quotes` |
| `hasbrouck_information_share` | tick multi-venue prices |
| `gonzalo_granger_cs` | tick multi-venue prices |
| `realized_kernel_vol` | tick trades |
| `lee_mykland_jump` | intraday returns |
| `empirical_volume_curve` | intraday 5-min bars |
| `quote_to_trade_ratio` | Level 1 quotes + trades |
| `cancellation_rate` | `order_book_events` |
| `trade_size_distribution` | tick trade records |

**Verify (Classical school, black-box):**
```python
request = ApplyMetricsRequest(metrics=["cont_kukanov_ofi"], available_data_class="daily_ohlcv")
result = use_case.execute(request)

assert result.valid is False
assert "level_2_order_book" in result.errors[0].required_data_class
assert len(result.errors[0].proxy_candidates) > 0

# Same metric with intraday bars is still unavailable (needs L2, not just bars):
result2 = catalog.check("cont_kukanov_ofi", available_data_class="intraday_ohlcv")
assert result2.computable is False
```

**Also test:**
- Every metric in the "10 metrics with no daily proxy" list from the doc is catalogued.
- Diagnostics suggest proxy alternatives where applicable.
- Strategy referencing `effective_spread_taq` on OHLCV-only artifact is rejected at validation.
- No silent fallback to `corwin_schultz_spread` unless user explicitly requests the proxy.

---

### Scenario: External sentiment, macro, and derivatives metrics declare provider requirements
**Priority:** Must  
**Slice:** 4

**Gherkin:**
  Given a metric requiring external non-OHLCV data
  When no provider is configured
  Then Finbar reports the provider requirement and does not compute fake values

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| metric_name | string | `vix_regime`, `put_call_ratio`, `cot_positioning` | Known external metric |
| provider_configured | bool | false | No provider available |
| asset_class | enum | equity / crypto / futures | Determines relevance |

**Expected output / state change:**

Full catalog of external-data metrics:

| Metric | Required provider / data | Asset class |
|--------|--------------------------|-------------|
| `vix_level` | VIX market data symbol | Equity |
| `vix_regime` | VIX OHLCV + thresholds | Equity |
| `put_call_ratio` | Options market data provider | Equity / Futures |
| `aaii_sentiment` | AAII survey data provider | Equity |
| `cot_commercial_net` | CFTC/COT data provider | Futures |
| `cot_nonreportable_net` | CFTC/COT data provider | Futures |
| `social_sentiment_score` | Social sentiment API | All |
| `funding_rate` | CoinGlass or exchange API | Crypto |
| `open_interest` | CoinGlass or exchange API | Crypto |
| `open_interest_delta_1h` | CoinGlass or exchange API | Crypto |
| `open_interest_delta_24h` | CoinGlass or exchange API | Crypto |
| `cumulative_volume_delta` | CoinGlass or exchange API | Crypto |
| `long_short_ratio` | CoinGlass or exchange API | Crypto |
| `liquidations_long_1h` | CoinGlass or exchange API | Crypto |
| `liquidations_short_1h` | CoinGlass or exchange API | Crypto |
| `liquidations_long_24h` | CoinGlass or exchange API | Crypto |
| `liquidations_short_24h` | CoinGlass or exchange API | Crypto |
| `funding_rate_annualised` | CoinGlass or exchange API | Crypto |
| `market_beta` | Benchmark/index OHLCV + instrument universe | All |
| `sector_relative_strength` | Sector/index OHLCV universe | Equity |
| `cross_asset_correlation` | Multi-asset OHLCV universe | All |

**Verify (Classical school, black-box):**
```python
result = catalog.check("put_call_ratio", available_data_class="daily_ohlcv")

assert result.computable is False
assert "options_provider" in result.required_providers
assert result.confidence == "unavailable"

# Crypto metrics with CoinGlass provider configured:
result2 = catalog.check("funding_rate", available_data_class="external_provider",
                          providers_configured=["coinglass"])
assert result2.computable is True
```

**Also test:**
- Existing CoinGlass derivatives metrics are reported as `available` when provider is configured.
- Equity-only sentiment metrics are marked `not_applicable` for crypto symbols.
- Provider errors produce `unavailable` diagnostics, not zero-valued columns.
- Every external metric lists its provider requirement and asset-class applicability.
- `market_beta` requires benchmark symbol to be specified.
