# ADRs — Integrate New Market Metrics

Only write architecture decisions that arose during the interview. Use ADR format.

---

## ADR-1: Merge StrategyIndicatorCatalog + StaticMarketMetricCatalog into one UnifiedMetricCatalog

**Context**

Two objects both called "catalog" exist today:

- `StrategyIndicatorCatalog` (in `parser/`) — a `_FIXED` dict that the YAML
  parser consults to accept/reject indicator names. It answers
  `supports_concrete(name)`, `resolve(type, period)`.
- `StaticMarketMetricCatalog` (in `domain/services/`) — a richer registry of
  `MarketMetricDefinition` entries that answers `check(name, data_class)`
  (capability) and `resolve_best(concept, ...)` (dual-path).

Keeping them separate risks the **name-sync invariant** (Invariant #1): a name
could be in one catalog but not the other, causing the parser to accept a name
that has no handler (silent NaN) or the capability layer to report "unknown" for
a name the parser accepts. The whole point of this spec is that "all indicators
and metrics can be used in strategies," so the two views of the metric universe
must agree.

**Decision**

Merge into a single `UnifiedMetricCatalog` (in `parser/unified_metric_catalog.py`)
that implements BOTH `IndicatorCapabilityProvider` (parser-side methods:
`resolve`, `supports_concrete`, `accepts_period`) AND `MarketMetricCatalog`
(capability-side methods: `check`, `resolve_best`, `get`, `list`). The unified
catalog holds one list of `MarketMetricDefinition` entries and derives the
parser-side answers from it.

The old `StrategyIndicatorCatalog` and `StaticMarketMetricCatalog` classes are
removed; existing imports are updated to point at `UnifiedMetricCatalog`.

**Consequences**

- ✅ Name-sync becomes structurally impossible to violate — there's one list.
- ✅ The parser gains capability awareness for free (it can warn "this metric
  needs intraday data" at parse time).
- ✅ Scenario 1.3 can verify the set agreement with one assertion.
- ⚠️ Larger class (~300 lines) — mitigated by extracting the static `_METRICS`
  list into a separate module (`_metric_registry.py`) so the catalog class
  stays under the 150-line limit.
- ⚠️ Migration: every `from ...strategy_indicator_catalog import` and
  `from ...static_market_metric_catalog import` must be updated. Mechanical.

---

## ADR-2: Rolling-window wrapper for scalar calculators

**Context**

About 10 of the new calculators return a single scalar (not a Series):
`roll_spread`, `liu_illiq`, `bao_pan_zhou_cost`, `resiliency_autocorr`,
`hurst_exponent`, `cross_price_leadership`, `volume_weighted_is`,
`opening_price_leadership`, `effective_tick_spread`, `lot_zero_return_spread`.

For a backtest, strategies need a value **per bar**. Broadcasting the scalar as
a constant is useless (the market changes over time).

**Decision**

Create `rolling_scalar_series(calculator, *args, window=20, **kwargs)` in
`indicators/rolling_scalar_wrapper.py`. It applies the scalar calculator over a
trailing `window`-bar slice at each bar, returning a `pd.Series`. Bars before
the warm-up period (`window - 1`) are NaN.

Handlers that wrap scalar calculators call `rolling_scalar_series` instead of
calling the calculator directly.

**Consequences**

- ✅ Every metric produces a time-varying Series, suitable for strategies.
- ✅ Single helper, reused by ~10 handlers — no duplication.
- ⚠️ Default window (20) is a sensible default but not always optimal. Handlers
  expose a `lookback` parameter so strategy YAMLs can override it
  (e.g. `roll_spread` already takes `lookback`).
- ⚠️ Performance: O(n × window) per scalar metric. Acceptable for n ≤ ~50k bars
  (intraday). For larger frames, vectorize later if profiling shows it's hot.

---

## ADR-3: No-lookahead as-of merge for derivatives data

**Context**

Derivatives data (funding, OI, liquidations) is fetched as a separate time
series with its own timestamps. It must be joined onto the OHLCV bar frame so
strategies can read it. A naive `merge_asof` on the same timestamp would let a
bar at time T see derivatives data stamped T — **lookahead bias** (the bar at T
hasn't closed yet when the derivatives value is published).

The existing `merge_timeframes` function (`indicators/bar_merger.py`) already
solves this for informative timeframes by offsetting availability to
`timestamp + interval_offset`.

**Decision**

Create `merge_derivatives_asof(ohlcv_df, derivatives_rows, interval)` in
`infrastructure/services/derivatives_merger.py` that reuses the same offset
logic: a derivatives row timestamped T is only available at bar T + interval.
Internally it builds an availability index and forward-fills.

The dispatcher calls `merge_derivatives_asof` before running OHLCV calculators
when any derivatives metric is requested (Invariant #5 — calculators stay pure).

**Consequences**

- ✅ Backtests are lookahead-free; consistent with `merge_timeframes`.
- ✅ Reuses proven offset logic — no new time-math.
- ⚠️ Derivatives data must be pre-fetched (via `fetch_derivatives`) before the
  backtest/job runs. Missing data → NaN column → conditions False (not a crash).
- ⚠️ The merge happens per-symbol; multi-symbol portfolio backtests call it
  once per asset.

---

## ADR-4: Confidence honesty invariant

**Context**

`StaticMarketMetricCatalog.check()` returns `computable=True/False`. If it
returns `True` for a metric that has no handler (or no data), the MCP/API
discovery layer lies to agents. An AI agent would request a metric that can't
actually be computed, wasting a backtest cycle or producing a silent all-NaN
column with no explanation.

**Decision**

The unified catalog's `check()` method returns `computable=True` ONLY when:
1. The metric has a registered handler (or it's a derivatives metric with data
   in the repository), AND
2. The requested `data_class` satisfies the metric's `required_data_classes`.

Otherwise it returns `computable=False` with a clear `warnings` tuple
explaining why (e.g. "not yet implemented", "needs intraday data",
"run fetch_derivatives first").

The `implemented` flag on `MarketMetricDefinition` must reflect whether a
handler is actually registered. A test (scenario 1.3) verifies the set
agreement between catalogued names and handler names.

**Consequences**

- ✅ Agents and users always know the true state — no wasted cycles.
- ✅ The dual-path resolver can confidently pick the best available path.
- ⚠️ Adding a new metric requires updating both the catalog entry AND registering
  a handler. The scenario 1.3 test catches omissions at CI time.
