# Domain Model — All-Metrics Causal Streaming Parity

## Definitions

### Causal prefix oracle
For a metric `m` and bar index `t`, the oracle value is:

```python
prefix = bars[: t + 1]
expected = PandasTaIndicatorCalculator().calculate(frame(prefix), [m]).iloc[-1][m]
```

This is the only correctness oracle for live-parity mode. It differs from legacy full-frame batch row `t` for indicators whose historical rows can see future bars in the same frame/session.

### Streaming-correct metric
A catalog metric is streaming-correct when the package streaming engine returns the causal prefix oracle value for every sampled prefix after warmup, within the metric's tolerance and with the correct logical type.

### Streaming-unsupported metric
Temporary rollout state: a catalog metric whose streaming implementation is not yet proven against the causal prefix oracle. Unsupported metrics must not silently drive trades in default backtests.

### Live-parity-safe backtest
A backtest whose strategy decisions used causal enriched rows for all required strategy metrics. `live_parity_safe=True` means no full-frame lookahead enrichment was used for signal decisions.

## Entities / Value Objects

| Name | Fields | Behaviour | Location |
|---|---|---|---|
| `MetricValueComparator` | `metric_name`, `tolerance`, `type_policy` | Compares numeric/string/bool/NaN values according to public metric contract | `finbar_strategy_runtime.domain.services` |
| `StreamingCoverageEntry` | `metric_name`, `label`, `reason`, `last_verified_at`, `tolerance` | One row in the coverage matrix | `domain/entities` |
| `StreamingCoverageMatrix` | `entries: dict[str, StreamingCoverageEntry]` | Exhaustive package-owned metric coverage state | `domain/entities` |
| `StreamingCoverageReport` | `correct`, `unsupported`, `silent_wrong`, `loud_nan_mismatch` | Result of a sweep or strategy classification | `domain/entities` |
| `CausalMetricSample` | `metric_name`, `index`, `got`, `expected`, `status` | Diagnostic row for parity failures | `domain/entities` |
| `CausalEnrichedBar` | existing: timestamp + scalar values | Latest causally enriched primary row | existing package entity |
| `FrameDependencyReport` | existing | Flags frame-dependent / non-live-safe batch results | existing package entity |

## Interfaces

### `CausalMetricOracle`
Pure test-support/domain service used by parity sweeps.

```python
class CausalMetricOracle(ABC):
    def expected_at(self, bars: list[dict], metric_name: str, index: int) -> Any: ...
```

Concrete implementation delegates to `PandasTaIndicatorCalculator` on the prefix. It is not used in production loops because it is intentionally expensive.

### `StreamingCoverageClassifier`
Package service used by Finbar and Finbot.

```python
class StreamingCoverageClassifier(ABC):
    def classify_metric(self, metric_name: str) -> StreamingCoverageEntry: ...
    def classify_indicators(self, metric_names: list[str]) -> StreamingCoverageReport: ...
```

During rollout it gates backtests away from unsupported metrics. After Slice 2 it should report every catalog metric as `STREAMING_CORRECT`.

### `CausalStreamingEnricher`
Single-timeframe package interface.

```python
class CausalStreamingEnricher(ABC):
    def update(self, bar: dict) -> CausalEnrichedBar: ...
    def latest(self) -> CausalEnrichedBar | None: ...
    def reset(self) -> None: ...
```

Implemented by `StreamingIndicatorEngine` plus feature calculation for single-timeframe strategies.

### `MultiTimeframeCausalStreamingEnricher`
MTF package interface consumed by Finbar backtests and Finbot live/replay.

```python
class MultiTimeframeCausalStreamingEnricher(ABC):
    def update(self, timeframe_alias: str, bar: dict) -> CausalEnrichedBar | None: ...
    def latest(self) -> CausalEnrichedBar | None: ...
    def reset(self) -> None: ...
```

Rules:
- Informative bars update informative state only.
- A primary bar update emits the latest primary enriched row.
- Informative values are merged as-of only if the informative candle closed at or before the primary decision time plus the declared availability offset.
- Output is a flat scalar dict ready for `JsonRuleBasedStrategy.on_bar`.

## Metric Families and Required Implementation Strategy

| Family | Examples | Required strategy |
|---|---|---|
| O(1) rolling/recursive | `sma_*`, `ema_*`, `rsi_*`, `atr`, `macd*`, `bb_*`, `adx`, `ibs`, `rvol` | Dedicated streaming state, tight parity vs prefix oracle |
| Session cumulative | `vwap`, session VP/AMT, `cumulative_signed_volume_ofi` | Session-aware state with timestamp/session reset; no global-from-start leakage |
| Rolling-window VP | `rvp_poc/vah/val_48/96/336` | Dedicated ring-buffer VP state matching prefix oracle; stable bucket-grid semantics |
| Composite / multi-day VP | `cvp_*`, `vp_*_5d/20d` | Dependency-aware causal recompute or dedicated session-deque state |
| Daily/session aggregators | `daily_vpin`, `intraday_volume_curve`, `empirical_volume_curve`, daily return moments | Track daily/session windows; old 50-bar fallback is forbidden |
| Statistical/regime | `hurst_exponent`, `bipower_variation`, `realized_*`, `market_regime`, `fractal_regime`, `day_type_classification`, `breakout_*` | Window/session lookback derived from metric definition; emit NaN only when prefix oracle does |
| Warmup-sensitive/proxy | `alligator_*`, `proxy_atr`, `proxy_iv`, `proxy_expected_move`, `parametric_u_shape` | Correct warmup and recursive seed handling; explicit tolerance |
| Derived classifiers | `profile_shape`, `is_b_shape`, `is_neutral_shape` | Compute dependencies causally first; preserve bool/string semantics |

## DTO / Boundary Data

### Backtest result metadata
Existing DTO fields are required on every backtest path:

| Field | Meaning |
|---|---|
| `enrichment_mode` | Effective mode actually used (`live_parity_streaming` or `batch_full_frame`) |
| `live_parity_safe` | True only when signal decisions used causal enrichment for all required metrics |
| `parity_warnings` | Human-readable warnings for fallback, unsupported metrics, or research-mode batch lookahead |

### Package API for Finbot
Finbot should depend only on package DTO/entities:
- `TimeframeDeclaration`
- `CausalEnrichedBar`
- `MultiTimeframeCausalStreamingEnricher`
- `StreamingCoverageClassifier`
- `RequiredDataValidator` / readiness result
- `JsonRuleBasedStrategy`

No Finbar application DTO may be required by Finbot.

## Entity vs ORM Separation
No ORM entities are introduced. Coverage matrix is a committed JSON fixture/resource in the package. Backtest artifacts may persist `enrichment_mode`, but persistence models remain in Finbar infrastructure and map to application DTOs.
