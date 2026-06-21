# Scenarios — All-Metrics Causal Streaming Parity

All tests follow Classical/Detroit + black-box principles: use real parsers, calculators, enrichers, strategy objects, and deterministic fixtures; fake only external boundaries; assert returned values and backtest outcomes, never internal call sequences.

## Slice 1 — Safety Gate and Causal Oracle

### Scenario 1: Catalog coverage matrix classifies every metric
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given all concrete names from the unified metric catalog
  When the streaming coverage matrix is loaded
  Then every metric is classified as `STREAMING_CORRECT` or `STREAMING_UNSUPPORTED`
  And no accepted strategy metric is unknown to the classifier

**Input table:**
| Field | Type | Example | Constraints |
|---|---|---|---|
| catalog_names | set[str] | 250 names | From `UnifiedMetricCatalog.supported_concrete_names()` |
| coverage_matrix | JSON | `streaming_coverage_matrix.json` | One entry per catalog metric |

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| Matrix keys equal catalog names | Set equality |
| No `UNKNOWN` label | Iterate all names |
| Each unsupported entry includes a reason | Inspect matrix entry |

**Verify:**
```python
catalog = UnifiedMetricCatalog().supported_concrete_names()
matrix = StreamingCoverageMatrix.load_default()
assert set(matrix.names()) == set(catalog)
for name in catalog:
    entry = matrix.entry_for(name)
    assert entry.label in {"STREAMING_CORRECT", "STREAMING_UNSUPPORTED"}
    if entry.label == "STREAMING_UNSUPPORTED":
        assert entry.reason
```

**Also test:**
- A typo metric (`"not_a_metric"`) raises a clear `UnknownMetricError`.
- The matrix is exported by the package, not by Finbar app code.

### Scenario 2: Causal prefix oracle defines correctness for every metric
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given deterministic multi-session OHLCV bars
  And a metric name
  When the streaming engine ingests bars through row `t`
  Then the streaming value at `t` equals the batch calculator run on the prefix `bars[:t+1]`, taking the last row
  And it never uses later rows from the same full frame

**Input table:**
| Field | Type | Example | Constraints |
|---|---|---|---|
| bars | list[OHLCV] | 30 sessions of 30m bars | Sorted, timestamped |
| metric | str | `"vwap"`, `"vp_poc"`, `"hurst_exponent"` | Any catalog metric |
| t | int | 17, 95, final row | `0 <= t < len(bars)` |

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| `stream[t][metric] == prefix_batch_last(metric, bars[:t+1])` | Numeric/string/bool comparator |
| Full-frame batch row `t` is not the oracle for session-dependent metrics | Regression fixture locks known divergence |

**Verify:**
```python
engine = StreamingIndicatorEngine(indicators=[metric])
for i, bar in enumerate(bars):
    got = engine.update(bar).values.get(metric)
    expected = batch_calc.calculate(frame(bars[: i + 1]), [metric]).iloc[-1][metric]
    assert_equivalent_metric_value(got, expected, metric)
```

**Also test:**
- Known lookahead-sensitive fixture: SOL row 17 session VP diverges from full-frame batch but equals prefix oracle.
- Bool/string classifiers compare by value, not float coercion.
- NaN is allowed only if the prefix oracle is also NaN and the metric is still warming up.

### Scenario 3: Causal default never silently trades on unsupported metrics
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a strategy requiring at least one `STREAMING_UNSUPPORTED` metric
  When Finbar runs a backtest with default `live_parity_streaming`
  Then the run does not silently use the broken streaming value
  And it either falls back to `batch_full_frame` with `live_parity_safe=False` and warnings, or fails with an explicit unsupported-metric error

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| No silent streaming result is returned | Inspect result metadata |
| Warning/error names all unsupported metrics | Inspect `parity_warnings` or exception |
| If fallback is chosen, result mode is `batch_full_frame` | Inspect DTO |

**Verify:**
```python
strategy = strategy_using("rvp_poc_48")
result = backtest_use_case.execute(BacktestStrategyDefinitionRequest(definition=strategy, bars=bars))
assert result.result.live_parity_safe is False
assert result.result.enrichment_mode in {"batch_full_frame", "failed"}
assert any("rvp_poc_48" in warning for warning in result.result.parity_warnings)
```

**Also test:**
- A strategy using only `STREAMING_CORRECT` metrics stays in `live_parity_streaming` and is marked safe.
- Explicit `batch_full_frame` request does not emit an unsupported-streaming warning.

## Slice 2 — Fix All Metric Families

### Scenario 4: Rolling-window VP (`rvp_*`) is causal and matches prefix oracle
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given `rvp_poc_N`, `rvp_vah_N`, and `rvp_val_N` for N in {48, 96, 336}
  When bars stream one at a time
  Then each latest value equals the prefix oracle for the same N
  And the implementation uses a stable bucket-grid semantic consistent with the batch handler on that prefix

**Verify:**
```python
for metric in RVP_METRICS:
    assert_metric_matches_prefix_oracle(metric, bars, sample_indices=[48, 96, 336, len(bars)-1])
```

**Also test:**
- Window size is parsed from the metric name.
- A 336-window metric keeps enough history to compute row 336 and final row.
- No per-window grid drift relative to the prefix oracle.

### Scenario 5: Composite and multi-day VP (`cvp_*`, `vp_*Nd`) are dependency-aware
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given `cvp_poc/vah/val_5d/10d/20d` and `vp_poc/vah/val_5d/20d`
  When bars stream across enough sessions
  Then each latest value equals the prefix oracle
  And all transitive dependencies are computed causally before the dependent metric

**Verify:**
```python
for metric in CVP_AND_MULTI_DAY_VP_METRICS:
    assert_metric_matches_prefix_oracle(metric, multi_session_bars, sample_indices=session_close_indices)
```

**Also test:**
- Insufficient sessions produce the same NaN as the prefix oracle, not a made-up zero.
- Dependency order is tested by requesting only the dependent metric.

### Scenario 6: Session and daily aggregators keep session-causal state
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given session/daily aggregators such as `vwap`, `daily_vpin`, `intraday_volume_curve`, `empirical_volume_curve`, `cumulative_signed_volume_ofi`, daily return moments, and realized-volatility metrics
  When bars stream across session boundaries
  Then each metric resets/rolls exactly as the prefix oracle does

**Verify:**
```python
for metric in SESSION_AND_DAILY_AGGREGATORS:
    assert_metric_matches_prefix_oracle(metric, multi_session_bars, sample_indices=[first_session_end, second_session_mid, len(bars)-1])
```

**Also test:**
- `vwap` resets on session boundary.
- The first bar of a new session does not retain previous-session cumulative volume unless the metric definition explicitly requires it.
- Zero-volume bars follow the prefix oracle.

### Scenario 7: Statistical and regime metrics have sufficient causal history
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given metrics with large lookbacks (`hurst_exponent`, `bipower_variation`, `realized_kurtosis/skewness/vol_5m`, `return_volume_correlation`, `market_regime`, `fractal_regime`, `day_type_classification`, `breakout_quality`, `breakout_signal`, `premium_discount_zone`, `price_vs_sma20`, `balance_status`)
  When the stream has enough bars/sessions
  Then the latest value equals the prefix oracle
  And before enough history exists, readiness and NaN behaviour match the oracle

**Verify:**
```python
for metric in STAT_REGIME_METRICS:
    assert_metric_matches_prefix_oracle(metric, long_multi_session_bars, sample_indices=[99, 250, len(bars)-1])
```

**Also test:**
- The minimum lookback reported in the metric catalog matches the implementation readiness threshold.
- No metric is capped by the old 50-bar default if it needs more.

### Scenario 8: EMA/proxy/warmup-sensitive metrics converge exactly enough
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given warmup-sensitive recursive/proxy metrics (`alligator_jaw/teeth/lips`, `proxy_atr`, `proxy_iv`, `proxy_expected_move`, `parametric_u_shape`)
  When enough bars have streamed
  Then latest values match the prefix oracle within the metric tolerance

**Verify:**
```python
for metric in WARMUP_SENSITIVE_METRICS:
    assert_metric_matches_prefix_oracle(metric, bars, sample_indices=[100, 300, len(bars)-1])
```

**Also test:**
- Tolerance is explicit per family; no broad `rtol=1e-4` hiding drift.
- Warmup windows are derived from handler requirements.

### Scenario 9: Derived boolean/string classifiers preserve type semantics
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given derived classifiers such as `profile_shape`, `is_b_shape`, and `is_neutral_shape`
  When bars stream one at a time
  Then the classifier result equals the prefix oracle as the same logical type
  And bools are not silently coerced through misleading floats

**Verify:**
```python
for metric in ["profile_shape", "is_b_shape", "is_neutral_shape"]:
    assert_metric_matches_prefix_oracle(metric, bars, sample_indices=[100, 200, len(bars)-1])
```

**Also test:**
- `True`/`False` equality is semantic; `1.0`/`0.0` is accepted only if the public metric contract is numeric.
- If `profile_shape` is warming up, derived booleans match the prefix oracle, not a default false/true.

### Scenario 10: Full-catalog causal parity sweep is green
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given all catalog metrics and deterministic multi-session fixtures
  When the full-catalog causal sweep runs
  Then every metric is `STREAMING_CORRECT`
  And the unsupported set is empty

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| `unsupported == []` | Inspect sweep report |
| All sampled rows match prefix oracle | Sweep details |
| Coverage matrix labels all names `STREAMING_CORRECT` | Matrix fixture |

**Verify:**
```python
report = run_causal_streaming_sweep(catalog_names, fixtures)
assert report.unsupported == []
assert report.silent_wrong == []
assert report.loud_nan_mismatch == []
```

**Also test:**
- Sweep covers at least: deterministic synthetic bars, SOL parity fixtures, zero-volume bars, flat-price bars, and multi-session data.
- The matrix fixture update is committed with the implementation.

## Slice 3 — Backtest Integration

### Scenario 11: Finbar JSON-strategy backtests use causal streaming for all metrics by default
**Priority:** Must
**Slice:** 3

**Gherkin:**
  Given any valid strategy definition using catalog metrics
  When `BacktestStrategyDefinitionUseCase` runs without an explicit mode
  Then enrichment mode is `live_parity_streaming`
  And all strategy decisions use causally enriched rows
  And no unsupported-metric fallback occurs after Slice 2 is complete

**Verify:**
```python
result = backtest_definition_use_case.execute(request_with_any_catalog_strategy)
assert result.result.enrichment_mode == "live_parity_streaming"
assert result.result.live_parity_safe is True
assert result.result.parity_warnings == []
```

**Also test:**
- `batch_full_frame` remains opt-in and reports `live_parity_safe=False` when frame-dependent metrics are present.
- Existing execution primitives produce unchanged trade accounting for a pre-enriched frame.

### Scenario 12: Saved-strategy backtests consume the same package causal enricher
**Priority:** Must
**Slice:** 3

**Gherkin:**
  Given a strategy saved in Finbar and the same strategy submitted inline as JSON/YAML
  When both are backtested with default settings
  Then both use the package causal streaming enricher
  And their enriched frames, trades, and metrics match

**Verify:**
```python
saved = run_saved_strategy_backtest(strategy_id, mode="live_parity_streaming")
inline = run_inline_strategy_backtest(definition, mode="live_parity_streaming")
assert saved.result.trades == inline.result.trades
assert saved.result.summary == inline.result.summary
```

**Also test:**
- Indicator-job artifacts record `enrichment_mode=live_parity_streaming`.
- A stale batch artifact is not silently reused for a causal backtest.

### Scenario 13: Backtest result exposes causal safety metadata
**Priority:** Must
**Slice:** 3

**Gherkin:**
  Given a backtest result from any entry point
  When the result is serialized via API or MCP
  Then it includes `enrichment_mode`, `live_parity_safe`, and `parity_warnings`

**Verify:**
```python
body = client.post("/api/strategy-definitions/backtest", json=payload).json()
assert body["result"]["enrichment_mode"] == "live_parity_streaming"
assert body["result"]["live_parity_safe"] is True
assert body["result"]["parity_warnings"] == []
```

## Slice 4 — Finbot Shared-Package Contract

### Scenario 14: Package exposes a Finbot-ready causal enricher API
**Priority:** Must
**Slice:** 4

**Gherkin:**
  Given Finbot receives closed candles one at a time for primary and informative timeframes
  When it creates the package causal MTF enricher from a parsed strategy definition
  Then each closed candle update returns the latest causal enriched primary bar ready for `JsonRuleBasedStrategy.on_bar`

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| API takes raw bars/timeframe alias, not DataFrames only | Public interface |
| Latest output is a flat scalar dict | Inspect returned entity |
| Warmup/readiness is reported data-driven | Inspect readiness result |

**Verify:**
```python
enricher = CausalMultiTimeframeStreamingEnricher.from_strategy_definition(definition)
for event in closed_candle_events:
    latest = enricher.update(event.timeframe_alias, event.bar)
    if latest.is_ready:
        signal = JsonRuleBasedStrategy(definition).on_bar(latest.values, position=None)
        assert signal is not None
```

**Also test:**
- Informative updates alone do not emit a primary decision row unless the primary bar closed.
- The API is pure and imports no Finbar app or Finbot modules.

### Scenario 15: Finbot replay parity contract uses the same enriched rows as Finbar
**Priority:** Must
**Slice:** 4

**Gherkin:**
  Given the SOL 30m/1h parity fixtures and the production strategy
  When Finbar runs a causal backtest and Finbot replay feeds the same closed-candle stream through the package enricher
  Then the enriched rows passed into `JsonRuleBasedStrategy.on_bar` are identical
  And signal decisions occur on the same timestamps

**Verify:**
```python
finbar_rows = finbar_causal_enriched_rows(strategy, primary_bars, {"h1": info_bars})
finbot_rows = package_replay_enriched_rows(strategy, interleaved_events)
assert finbot_rows == finbar_rows
assert signal_timestamps(finbot_rows) == signal_timestamps(finbar_rows)
```

**Also test:**
- This is a package/contract test in Finbar; the full live-loop replay test lives in Finbot.
- The contract does not assert live exchange fills; Finbot live fills remain exchange-owned.
