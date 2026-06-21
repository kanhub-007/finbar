# Implementation Guide — All-Metrics Causal Streaming Parity

Implement in TDD slices. The package owns semantics; Finbar app wires the package; Finbot consumes the package contract later.

## Slice 1 — Safety Gate and Oracle

### Step 1.1: Add prefix-oracle test helpers
**Files:**
- `packages/strategy-runtime/tests/support/causal_metric_oracle.py` (new)
- `packages/strategy-runtime/tests/support/metric_value_assertions.py` (new)

Create helpers:
- `expected_prefix_value(metric, bars, index)`
- `assert_equivalent_metric_value(got, expected, metric)`
- `assert_metric_matches_prefix_oracle(metric, bars, sample_indices)`

The comparator handles numeric tolerance, `NaN` equivalence, bools, strings, and numpy scalar types.

**Verify:** small tests for numeric, NaN, bool, string comparisons.

**Common mistake:** comparing every value as `float`. This caused `is_b_shape` / `is_neutral_shape` confusion.

### Step 1.2: Commit the initial coverage matrix and classifier
**Files:**
- `packages/strategy-runtime/finbar_strategy_runtime/domain/entities/streaming_coverage_entry.py` (new)
- `packages/strategy-runtime/finbar_strategy_runtime/domain/entities/streaming_coverage_matrix.py` (new)
- `packages/strategy-runtime/finbar_strategy_runtime/domain/entities/streaming_coverage_report.py` (new)
- `packages/strategy-runtime/finbar_strategy_runtime/domain/services/streaming_coverage.py` (new)
- `packages/strategy-runtime/finbar_strategy_runtime/resources/streaming_coverage_matrix.json` (new)
- `packages/strategy-runtime/tests/contract/test_streaming_coverage_matrix.py` (new)

Generate a matrix from the reviewed findings:
- 22 `STREAMING_UNSUPPORTED` with reason `silent_wrong_value`
- 23 `STREAMING_UNSUPPORTED` with reason `nan_or_raise_mismatch`
- all remaining catalog names `STREAMING_CORRECT` if already proven by existing parity tests or sweep.

**Verify:** Scenario 1.

**Common mistake:** placing the matrix under Finbar app tests only. It must be package-owned because Finbot consumes it.

### Step 1.3: Gate Finbar default backtests
**Files:**
- `finbar/core/application/use_cases/backtest_strategy_definition.py`
- `finbar/core/application/live_parity_frame_builder.py`
- `finbar/core/application/dto/backtest_result.py` (if metadata gaps remain)

Before building a causal frame, classify the strategy's required indicators. During rollout:
- If all are correct: use `live_parity_streaming`, mark safe.
- If any are unsupported: either fail explicitly or fallback to `batch_full_frame` with `live_parity_safe=False` and warnings. Prefer fallback for backwards compatibility, but never silent fallback.

**Verify:** Scenario 3.

### Step 1.4: Add the full-catalog sweep script
**Files:**
- `scripts/generate_causal_streaming_coverage_matrix.py` (new)
- `packages/strategy-runtime/tests/contract/test_causal_streaming_catalog_sweep.py` (new or nightly marker)

The script:
1. Loads all metric names from `UnifiedMetricCatalog`.
2. Runs deterministic fixtures (synthetic multi-session, SOL parity, flat, zero-volume).
3. Samples multiple prefix indices per metric.
4. Writes the coverage matrix JSON.

The fast test validates matrix consistency; the full sweep can be marked slow/nightly but must be runnable locally.

**Verify:** Scenario 10 will fail initially until Slice 2 completes; mark expected unsupported set in Slice 1.

## Slice 2 — Fix Metric Families

### Step 2.1: Replace global 50-bar fallback with metric-derived history
**Files:**
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/streaming_indicator_engine.py`
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/windowed_indicator_state.py`

Rules:
- Use metric catalog `min_lookback` and handler-specific requirements.
- Session-count metrics must retain enough bars to cover sessions, not only bars.
- Metrics with explicit suffix windows (`_48`, `_96`, `_336`, `_5d`, `_20d`) derive window/session history from the suffix.

**Verify:** Scenarios 6, 7, 8 for metrics previously failing due to the old 50-bar cap.

### Step 2.2: Implement session-aware VWAP and cumulative session states
**Files:**
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/vwap_state.py` (new or fixed)
- session/cumulative state files as needed, one class per file

Fix:
- `vwap` resets by session according to timestamp.
- `cumulative_signed_volume_ofi`, `daily_vpin`, `intraday_volume_curve`, `empirical_volume_curve` track the same prefix-session semantics as batch-on-prefix.

**Verify:** Scenario 6.

### Step 2.3: Implement rolling-window VP state
**Files:**
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/rolling_volume_profile_state.py` (new)

Fix `rvp_poc_48/96/336`, `rvp_vah_*`, `rvp_val_*`:
- ring buffer for the last N bars
- stable bucket-grid semantics matching the prefix oracle
- recompute or incremental add/subtract is acceptable if performance budget passes; correctness first.

**Verify:** Scenario 4.

### Step 2.4: Implement composite and multi-day VP causal dependencies
**Files:**
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/composite_volume_profile_state.py` (new if needed)
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/windowed_indicator_state.py`

Fix `cvp_*` and `vp_*_5d/20d` by either:
- dedicated session-deque state, or
- dependency-aware prefix/window recompute that expands transitive dependencies and computes them in order.

Correctness requirement: matches prefix oracle at sampled rows, including mid-session.

**Verify:** Scenario 5.

### Step 2.5: Statistical/regime history fixes
**Files:** dedicated state classes or window sizing changes, one class per state if new.

Fix:
- `hurst_exponent`
- `bipower_variation`
- `realized_kurtosis`, `realized_skewness`, `realized_vol_5m`
- `daily_return_kurtosis`, `daily_return_skewness`
- `return_volume_correlation`
- regime/classifier metrics listed in Scenario 7.

**Verify:** Scenario 7.

### Step 2.6: Warmup-sensitive/proxy convergence fixes
**Files:** state/window sizing around proxy and alligator handlers.

Fix:
- `alligator_jaw`, `alligator_teeth`, `alligator_lips`
- `proxy_atr`, `proxy_iv`, `proxy_expected_move`
- `parametric_u_shape`

**Verify:** Scenario 8.

### Step 2.7: Derived classifier type/dependency fixes
**Files:**
- profile classifier streaming path / windowed dependency path

Fix:
- `profile_shape`
- `is_b_shape`
- `is_neutral_shape`

Ensure dependent bools do not default to the wrong value while `profile_shape` is warming up.

**Verify:** Scenario 9.

### Step 2.8: Regenerate matrix; unsupported set empty
Run:
```bash
python scripts/generate_causal_streaming_coverage_matrix.py --write
pytest packages/strategy-runtime/tests/contract/test_causal_streaming_catalog_sweep.py -q
```

Update `streaming_coverage_matrix.json`. All catalog entries should be `STREAMING_CORRECT`.

**Verify:** Scenario 10.

## Slice 3 — Finbar Backtest Integration

### Step 3.1: Make JSON-strategy backtest use package causal enricher for every metric
**Files:**
- `finbar/core/application/live_parity_frame_builder.py`
- `finbar/core/application/use_cases/backtest_strategy_definition.py`
- `startup/` factories as needed

Ensure frame building calls package services only for indicator semantics. Finbar app may orchestrate use cases, but no app-local indicator semantics.

**Verify:** Scenario 11.

### Step 3.2: Make saved-strategy path use package causal artifacts
**Files:**
- `finbar/core/application/dto/backtest_request.py`
- `finbar/infrastructure/services/indicator_job_runner.py`
- `finbar/core/application/use_cases/run_backtest.py`
- `finbar/core/application/saved_strategy_frame_assembler.py` (new if needed)

Add/plumb `enrichment_mode`. Indicator artifacts must store whether they were built causally or batch. A causal backtest must not reuse a stale batch artifact.

**Verify:** Scenario 12.

### Step 3.3: API/MCP metadata
**Files:**
- `finbar/presentation/api/routes/strategy_definition.py`
- `finbar/presentation/api/routes/analysis.py`
- `finbar/presentation/mcp/tools/strategy_definition.py`
- `finbar/presentation/mcp/tools/analysis.py`

Expose `enrichment_mode`, `live_parity_safe`, `parity_warnings` for both JSON and saved backtests.

**Verify:** Scenario 13.

## Slice 4 — Finbot Package Contract

### Step 4.1: Publish a stable package API for live candle updates
**Files:**
- `packages/strategy-runtime/finbar_strategy_runtime/domain/interfaces/multi_timeframe_streaming_enricher.py`
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/causal_multi_timeframe_streaming_enricher.py`
- package `__init__` exports where appropriate

Expose an API that Finbot can use with closed candle events:

```python
enricher = CausalMultiTimeframeStreamingEnricher.from_strategy_definition(definition)
latest = enricher.update(alias, bar)
```

**Verify:** Scenario 14.

### Step 4.2: Add package contract replay test
**Files:**
- `packages/strategy-runtime/tests/contract/test_finbot_causal_enricher_contract.py` (new)

Interleave primary/informative fixture events exactly as Finbot receives them. Assert the rows emitted on primary close equal Finbar's causal rows.

**Verify:** Scenario 15.

### Step 4.3: Document Finbot integration handoff
**Files:**
- `docs/finbot_causal_streaming_enricher_contract.md` (new)

Document:
- package imports Finbot should use
- warmup/readiness semantics
- informative update semantics
- no-lookahead merge rules
- coverage classifier usage
- what Finbot still owns (loop, websocket, exchange, live fills)

## Suggested Commit Cadence
1. Slice 1 safety gate + matrix.
2. One commit per metric family in Slice 2.
3. Matrix regeneration commit proving unsupported set is empty.
4. Finbar JSON + saved backtest integration.
5. Package API + Finbot contract docs/tests.
