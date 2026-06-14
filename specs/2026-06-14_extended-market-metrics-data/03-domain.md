# Domain Model — Extended Market Metrics and Data Requirements

## Entities
| Entity | Fields | Behaviour | Persisted? |
|--------|--------|-----------|------------|
| `MarketMetricDefinition` | name, family, description, output_columns, required_inputs, min_lookback, confidence (actual/proxy/approximation/unavailable), paper_reference, proxy_candidates | Describes one computable or unavailable metric | No; catalog is static/configured |
| `DataRequirement` | data_class, required_columns, interval_constraints, provider_requirements, min_bars | States data needed to compute a metric | No |
| `DataAvailability` | symbol, source, interval, data_class, start/end, available_columns, configured_providers | Describes current data | No |
| `MetricCapabilityResult` | metric, supported, computable, confidence, selected_metric (concrete column name for the chosen path), available_paths (ordered list of MetricResolutionPath), missing_data_classes, missing_providers, proxy_candidates, warnings | Result of capability check + auto-selected best path | No |
| `MetricCalculationRequest` | bars/artifact_id, metrics, options, available_data_metadata | Boundary DTO for use case | No |
| `MetricCalculationResult` | enriched_bars/artifact_id, applied_metrics, skipped_metrics, diagnostics | Output of calculation use case | App may persist artifact |
| `MetricDiagnostic` | metric_name, severity (error/warning/info), message, required_data_classes, proxy_candidates | User-facing error/warning | App may persist job diagnostics |

## Value Objects
| Name | Fields | Used where |
|------|--------|------------|
| `DataClass` | enum: `daily_ohlcv`, `intraday_ohlcv`, `trades`, `quotes`, `trades_and_quotes`, `level_2_order_book`, `order_book_events`, `external_provider` | Capability checks |
| `MetricFamily` | spread, volatility, liquidity_impact, order_flow, informed_trading, volume_profile, jump_tail_risk, intraday_seasonality, order_arrival, resiliency, information_share, price_action, trend_structure, vsa, sentiment, derivatives, portfolio, cross_asset | Catalog grouping |
| `MetricConfidence` | actual / proxy / approximation / unavailable | UI/API diagnostics |
| `MetricResolutionPath` | metric_name, required_data_class, required_columns, confidence, priority (1=highest) | One computation path for a conceptual metric; used by `resolve_best()` |
| `ProviderRequirement` | provider_name, provider_type, applicable_asset_classes, optional_symbol_mapping | External metrics |

## Interfaces (for DI)
| Interface | Methods | Implemented by |
|-----------|---------|----------------|
| `MarketMetricCatalog` | `get(name)`, `list(family=None)`, `check(name, availability)`, `resolve_best(concept, availability, force_proxy=False) -> MetricCapabilityResult` | `StaticMarketMetricCatalog` |
| `MarketMetricCalculator` | `calculate(frame, metrics, options) -> MetricCalculationResult` | `CompositeMarketMetricCalculator` |
| `MetricCalculatorStrategy` | `supports(metric)`, `calculate(frame, definition, options) -> frame` | One implementation per metric family |
| `DataAvailabilityProvider` | `describe(symbol, source, interval) -> DataAvailability` | Price cache / artifact adapters |
| `ExternalMetricProvider` | provider-specific `fetch` / `availability` methods | VIX / options / COT / sentiment / derivatives adapters |

## Complete metric families and data sufficiency

### Spread proxies (OHLCV — 7 metrics)
| Metric | Data class | Min bars | Confidence |
|--------|-----------|---------|------------|
| `corwin_schultz_spread` | daily/intraday OHLC | 20 | proxy |
| `roll_spread` | close | 20 | proxy |
| `abdi_ranaldo_spread` | OHLC | 20 | proxy |
| `effective_tick_spread` | close | 60 | proxy |
| `fong_holden_tran_spread` | OHLC | 20 | proxy |
| `chung_zhang_spread` | OHLC | 20 | proxy |
| `lot_zero_return_spread` | close | 60 | proxy |

### Volatility (OHLCV — 9 metrics)
| Metric | Data class | Min bars | Confidence | Status |
|--------|-----------|---------|------------|--------|
| `close_to_close_vol` | close | 20 | actual | New |
| `parkinson_vol` | HL | 20 | proxy | Existing `proxy_parkinson`, register separately |
| `garman_klass_vol` | OHLC | 20 | proxy | Existing `proxy_garman_klass`, register |
| `rogers_satchell_vol` | OHLC | 20 | proxy | Existing `proxy_rogers_satchell`, register |
| `yang_zhang_vol` | OHLC | 21 | proxy | Existing function, register as requestable |
| `gk_plus_overnight_vol` | OHLC | 20 | proxy | New |
| `meilijson_vol` | OHLC | 20 | proxy | New |
| `daily_return_skewness` | close | 60 | actual | New |
| `daily_return_kurtosis` | close | 60 | actual | New |

### Liquidity / impact (OHLCV — 8 metrics)
| Metric | Data class | Min bars | Confidence |
|--------|-----------|---------|------------|
| `amihud_illiq` | close, volume | 20 | proxy |
| `amivest_liquidity` | close, volume | 20 | proxy |
| `florackis_lambda` | close, volume | 20 | proxy |
| `hasbrouck_daily_lambda` | close, volume | 20 | proxy |
| `pastor_stambaugh_liquidity` | close, volume (multi-asset) | 60 | proxy |
| `liu_illiq` | volume | 21 | proxy |
| `turnover` | volume, shares | 1 | actual |
| `bao_pan_zhou_cost` | close | 20 | proxy |

### Order flow (OHLCV — 6 metrics)
| Metric | Data class | Min bars | Confidence |
|--------|-----------|---------|------------|
| `signed_sqrt_volume_ofi` | close, volume | 1 | proxy |
| `bvc_buy_volume` | close, volume, volatility | 20 | proxy |
| `bvc_sell_volume` | close, volume, volatility | 20 | proxy |
| `bvc_ofi` | close, volume, volatility | 20 | proxy |
| `cumulative_signed_volume_ofi` | close, volume | 20 | proxy |
| `return_volume_correlation` | close, volume | 60 | proxy |

### Informed trading (OHLCV — 2 metrics)
| Metric | Data class | Min bars | Confidence |
|--------|-----------|---------|------------|
| `daily_vpin` | close, volume, volatility | 50 | proxy |
| `spread_based_pin_proxy` | Corwin-Schultz + reversal | 20 | proxy |

### Jump / tail risk (OHLCV — 4 metrics)
| Metric | Data class | Min bars | Confidence |
|--------|-----------|---------|------------|
| `jump_gap_proxy` | OHLC | 20 | proxy |
| `extreme_return_flag` | close | 20 | proxy |
| `cc_rs_jump_proxy` | OHLC | 20 | proxy |
| `overnight_gap_proxy` | open, prev-close | 2 | proxy |

### Intraday seasonality (OHLCV + provider fields — 3 metrics)
| Metric | Data class | Min bars | Confidence |
|--------|-----------|---------|------------|
| `overnight_intraday_decomp` | OHLC | 20 | approximation |
| `parametric_u_shape` | volume | 20 | approximation |
| `first_last_hour_vol_fraction` | opening/closing volume fields | 20 | approximation |

### Order arrival (OHLCV + provider fields — 2 metrics)
| Metric | Data class | Min bars | Confidence |
|--------|-----------|---------|------------|
| `volume_to_trade_count_proxy` | volume, avg_trade_size | 20 | proxy |
| `trade_count_daily` | trade_count provider field | 1 | actual |

### Resiliency (OHLCV — 3 metrics)
| Metric | Data class | Min bars | Confidence |
|--------|-----------|---------|------------|
| `resiliency_autocorr` | close | 20 | proxy |
| `resiliency_spread_to_impact` | OHLCV (needs CS spread) | 20 | proxy |
| `inverse_amihud_resiliency` | close, volume | 20 | proxy |

### Information share (OHLCV — 5 metrics)
| Metric | Data class | Min bars | Confidence |
|--------|-----------|---------|------------|
| `cross_price_leadership` | close (multi-asset) | 60 | proxy |
| `volume_weighted_is` | volume (multi-asset) | 20 | proxy |
| `opening_price_leadership` | open (multi-asset) | 60 | proxy |
| `daily_cross_correlation` | close (multi-asset) | 60 | proxy |
| `daily_beta_ols` | close (multi-asset + benchmark) | 60 | proxy |

### Price action / trading theory (OHLCV — 66 metrics)

**Fibonacci** (10):
`fib_236_retrace`, `fib_382_retrace`, `fib_500_retrace`, `fib_618_retrace`, `fib_786_retrace`, `fib_1272_extension`, `fib_1618_extension`, `fib_2000_extension`, `fib_2618_extension`, `fib_confluence_score`

**Supply/Demand zones** (8):
`demand_zone_low`, `demand_zone_high`, `demand_zone_score`, `supply_zone_low`, `supply_zone_high`, `supply_zone_score`, `zone_failure_bullish`, `zone_failure_bearish`

**SMC approximations** (11):
`bullish_fvg`, `bearish_fvg`, `bullish_order_block`, `bearish_order_block`, `breaker_block_bullish`, `breaker_block_bearish`, `liquidity_sweep_high`, `liquidity_sweep_low`, `bos`, `choch`, `premium_discount_zone`

**VSA** (10):
`no_demand`, `no_supply`, `stopping_volume`, `climax_volume`, `effort_to_rise`, `effort_to_fall`, `effort_result_divergence`, `bag_holding`, `shakeout`, `test`

**Bill Williams** (9):
`williams_fractal_high`, `williams_fractal_low`, `alligator_jaw`, `alligator_teeth`, `alligator_lips`, `alligator_status`, `awesome_oscillator`, `accelerator_oscillator`, `zone_signal`

**Fractal / Hurst** (2):
`hurst_exponent`, `fractal_regime`

**Market Profile day types** (1):
`day_type_classification`

**Adaptive Markets regime** (1):
`market_regime`

**Dow Theory / trend structure** (6):
`swing_high_N` (generalize from existing `swing_high_20`), `swing_low_N`, `hh_hl_pattern`, `lh_ll_pattern`, `volume_trend_confirmation`, `trend_phase`

**Elliott Wave** (5 — catalogued, not implemented):
`elliott_wave_count`, `elliott_wave_phase`, `elliott_zigzag_correction`, `elliott_flat_correction`, `elliott_triangle_correction`

All price-action metrics have `confidence: "approximation"`. Elliott Wave metrics have status `unimplemented` with note: "requires dedicated wave-detection engine with 3 inviolable rule checks." Existing Wyckoff phase and profile shape indicators coexist unchanged.

### Dual-path resolution (actual vs. proxy auto-selection)
For every conceptual metric that has both an intraday (actual) and daily (proxy) computation path, the catalog defines ordered `MetricResolutionPath` entries. `MarketMetricCatalog.resolve_best(concept, availability)` auto-selects the highest-confidence path. Users may override with `force_proxy=true`. The `MetricCapabilityResult.selected_metric` field names the concrete column computed.

### Non-OHLCV metrics (catalogued as unavailable until data providers exist)

**Require `trades_and_quotes`** (8):
`effective_spread_taq`, `quoted_spread`, `realized_spread_taq`, `lee_ready_classification`, `kyle_lambda`, `hasbrouck_var_impact`, `trade_classified_ofi`, `price_reversion_speed`

**Require `level_2_order_book`** (5):
`cont_kukanov_ofi`, `order_book_depth_profile`, `order_book_shape`, `depth_recovery_time`, `almgren_chriss_impact`

**Require `order_book_events`** (4):
`noi_from_lob_events`, `iceberg_detection`, `spoofing_detection`, `absorption_detection`, `cancellation_rate`

**Require intraday bars** (8):
`realized_vol_5m`, `realized_vol_15m`, `realized_vol_1h`, `bipower_variation`, `realized_skewness`, `realized_kurtosis`, `intraday_volume_curve`, `lee_mykland_jump`, `empirical_volume_curve`

**Require tick trades** (4):
`realized_kernel_vol`, `order_arrival_rate`, `intraday_vpin`, `trade_size_distribution`

**Require multi-venue tick data** (2):
`hasbrouck_information_share`, `gonzalo_granger_cs`

**Require `trades_and_quotes` + classified** (2):
`true_pin_easley`, `odd_lot_ratio`

**Require Level 1 quotes** (1):
`quote_to_trade_ratio`

### External provider metrics (catalogued — 21 metrics)

**Derivatives — crypto** (9, many already supported via CoinGlass in Finbar):
`funding_rate`, `open_interest`, `open_interest_delta_1h`, `open_interest_delta_24h`, `cumulative_volume_delta`, `long_short_ratio`, `liquidations_long_1h`, `liquidations_short_1h`, `liquidations_long_24h`, `liquidations_short_24h`, `funding_rate_annualised`

**Equity sentiment / macro** (5):
`vix_level`, `vix_regime`, `put_call_ratio`, `aaii_sentiment`, `social_sentiment_score`

**Futures / COT** (2):
`cot_commercial_net`, `cot_nonreportable_net`

**Portfolio / cross-asset** (3):
`market_beta`, `sector_relative_strength`, `cross_asset_correlation`

## Entity vs ORM separation
- Metric definitions and calculation outputs are domain/application concepts.
- Persisted enriched bars remain artifacts in Finbar infrastructure.
- External provider API payloads must be mapped to domain DTOs before crossing into application use cases.
- No provider SDK/API type may leak into domain or application layers.

## Existing-to-new mapping
The following existing Finbar indicators are **re-catalogued** under the metric registry (they continue to work via the existing indicator pipeline unchanged; the catalog also registers them):

| Existing column / function | New metric name in catalog |
|---|---|
| `proxy_parkinson` | `parkinson_vol` |
| `proxy_garman_klass` | `garman_klass_vol` |
| `proxy_rogers_satchell` | `rogers_satchell_vol` |
| `proxy_vwap` | `vwap_typical_price_proxy` |
| `proxy_ibs` | `ibs` (already registered) |
| `proxy_atr` | `atr` (already registered) |
| `proxy_ib_high` / `proxy_ib_low` | `ib_high_proxy` / `ib_low_proxy` |
| `yang_zhang_vol` (pure function, unregistered) | `yang_zhang_vol` (register as indicator column) |
| `wyckoff_phase` and boolean wrappers | Existing, unchanged |
| `profile_shape` and boolean wrappers | Existing, unchanged |
| `is_coiled` / `coil_intensity` | Existing, unchanged |
