# Unified Catalog: Single Source of Truth for the Parser Gate

## User Story

**As a** strategy developer (human or AI agent),
**I want to** reference any catalogued metric that has a registered
computation handler — VSA signals (`bag_holding`, `stopping_volume`),
SMC/ICT (`bos`, `choch`, `bullish_fvg`), Bill Williams (`alligator_jaw`,
`awesome_oscillator`), Fibonacci, microstructure proxies, derivatives,
and regime classifiers (`market_regime`, `hurst_exponent`) — by name in
my strategy YAML,
**so that** I can build strategies using the full metric catalog, and
**so that the next metric added to the catalog is automatically usable
without anyone touching catalog wiring code**.

## Context — Comprehensive Bug Investigation

### How the bug was discovered

While building a regime-conditional strategy library (VSA, SMC, Wyckoff,
Bill Williams), a strategy referencing `bag_holding` and
`effort_result_divergence` was submitted to
`validate_strategy_definition`. It was rejected:

```json
{"path": "$.indicators[8]", "code": "unsupported_indicator",
 "message": "unsupported indicator type/period: bag_holding_None"}
```

Yet `list_market_metrics` reported both as `computable: true`,
`implemented: true`, and `compute_trading_metrics` / `compute_indicators`
produced the columns with real data. The metrics were registered,
computed, and validated by the capability layer — but rejected by the
strategy parser. A split existed between two code paths.

### Root cause — duplicated rule across 6 methods, only 2 kept in sync

`UnifiedMetricCatalog` (commit `4c09a0d`, *"feat: unified catalog,
name-sync invariant"*) merges a legacy hard-coded whitelist
(`StrategyIndicatorCatalog._FIXED`, ~95 entries) with the unified
`_metric_registry` (~116 `MarketMetricDefinition` entries). Six
parser-side methods each independently answer variants of *"is this
registry metric usable in a strategy?"* The rule
**"usable = in `_by_name` AND in `_handled_names`"** is encoded in each
of them. A runtime audit shows it was only kept current in 2:

| Method | Consults `_by_name` | Consults `_handled_names` | Status |
|---|---|---|---|
| `resolve` | ❌ | ❌ | **broken (the bug)** |
| `as_dict` | ❌ | ❌ | **broken (2nd symptom)** |
| `supports_concrete` | ✅ | ✅ | correct |
| `supported_concrete_names` | ✅ | ✅ | correct |
| `requires_period` / `accepts_period` | ❌ | ❌ | safe-by-coincidence |

The parser's validation gate is `resolve()` (called from
`StrategyIndicatorResolver._parse_one()`). When `resolve()` returns
`None`, the indicator is rejected with `unsupported_indicator`. So the
2 methods that were never updated are exactly the ones that matter most
for strategy authoring.

### Runtime proof (reproduced in the installed package)

```python
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog
c = UnifiedMetricCatalog()
for m in ['bag_holding','effort_result_divergence','market_regime',
          'hurst_exponent','bos','choch','bullish_fvg','alligator_jaw']:
    print(f"{m:32} by_name={m in c._by_name!s:5} handled={m in c._handled_names!s:5} "
          f"supports_concrete={c.supports_concrete(m)!s:5} resolve={c.resolve(m,None)}")
```

Every row shows the mismatch: `supports_concrete` → True, `resolve` →
None. The parser uses `resolve`.

### Blast radius — 116 metrics blocked, not a handful

A full enumeration confirms **116 catalogued metrics with registered
handlers are blocked by `resolve()`**. Entire theory families the
strategy library needs are unusable:

| Theory family | Blocked metrics (representative) |
|---|---|
| VSA | `bag_holding`, `effort_result_divergence`, `stopping_volume`, `no_demand`, `no_supply`, `climax_volume`, `shakeout`, `effort_to_rise`, `effort_to_fall`, `vsa_test_signal` |
| SMC / ICT | `bos`, `choch`, `bullish_fvg`, `bearish_fvg`, `bullish_order_block`, `bearish_order_block`, `breaker_block_bullish`, `breaker_block_bearish`, `liquidity_sweep_high`, `liquidity_sweep_low`, `premium_discount_zone` |
| Bill Williams | `alligator_jaw`, `alligator_teeth`, `alligator_lips`, `alligator_status`, `awesome_oscillator`, `accelerator_oscillator`, `williams_fractal_high`, `williams_fractal_low`, `zone_signal` |
| Fibonacci | `fib_382_retrace`, `fib_500_retrace`, `fib_618_retrace`, `fib_1618_extension`, `fib_confluence_score` |
| Microstructure | `corwin_schultz_spread`, `roll_spread`, `amihud_illiq`, `yang_zhang_vol`, `parkinson_vol`, `garman_klass_vol`, `rogers_satchell_vol`, `daily_vpin`, `bvc_ofi` |
| Derivatives | `funding_rate`, `open_interest`, `open_interest_delta_1h/24h`, `liquidations_long/short_1h/24h`, `cumulative_volume_delta`, `long_short_ratio` |
| Regime | `market_regime`, `hurst_exponent`, `fractal_regime`, `day_type_classification`, `trend_phase` |
| Trend structure | `hh_hl_pattern`, `lh_ll_pattern`, `swing_high_n`, `swing_low_n`, `volume_trend_confirmation` |

### The compute path works end-to-end (the fix is wiring, not math)

`PandasTaIndicatorCalculator` produces every blocked column:

```python
calc = PandasTaIndicatorCalculator()
out = calc.calculate(df, ['bag_holding','effort_result_divergence',
                          'market_regime','hurst_exponent','bos','choch'])
# → all 6 columns produced, bag_holding = 120/120 non-null on test data
```

So there is no downstream obstacle: the parser records
`concrete_name = "bag_holding"`, and the column lookup matches what the
calculator writes. Only the catalog wiring is broken.

### Why the existing test did not catch it

`test_unified_catalog.py::TestNameSyncInvariant::test_every_handler_accepted_by_parser`
has the correct intent but asserts on `supports_concrete()` (which works)
**not** `resolve()` (which is the actual parser gate). The invariant
test passes while the real bug persists. This spec strengthens the
invariant to assert on `resolve()` AND to assert the two methods agree.

### Git history confirms the design intent (this is a bug, not a restriction)

| Commit | Message | Relevance |
|---|---|---|
| `4c09a0d` | `feat: unified catalog, name-sync invariant` | Built `UnifiedMetricCatalog` to eliminate the name-sync gap. The merge was applied inconsistently across methods. |
| `ee6f725` | `fix: remove 44 unsupportable metrics, enforce handler-required parser gate` | Stated intent: *"handler-required parser gate."* Only wired into `supports_concrete()`. |
| `a678ac8` | `fix: comprehensive code review` | Most recent; did not catch this. |

The class docstring states the intent unambiguously:
> *"A catalogued metric is only accepted when it has a registered handler
> (can actually compute a column)."*

### Design weakness that allowed the drift

The rule "registry name + handler = usable" had **no first-class
representation** — it was copy-pasted across 6 methods as raw
`if name in self._by_name and name in self._handled_names:` checks.
Patching `resolve()` and `as_dict()` would fix *this* instance but
leave the duplication intact: the next contributor adding a 5th method
(or editing `resolve` again) could recreate the exact same bug class and
only discover it at CI time (if the regression test isn't deleted).

This spec therefore fixes the bug **and** removes the structural cause:
the usable-set rule is promoted to a first-class **Value Object**
(`UsableMetricSet`) that owns the rule once, and the catalog is guarded
by a **construction-time consistency check** (Design by Contract) so
any drift fails the process at first import.

### Same bug class discovered on the legacy side (during implementation)

A probe while implementing the registry fix revealed that
`StrategyIndicatorCatalog.resolve()` has the **identical**
resolve/supports_concrete asymmetry — for rolling-VP pattern names not
hardcoded in `_FIXED` (`vp_poc_10d`, `rvp_poc_100`, `cvp_poc_50d`, …).
`supports_concrete()` accepts them via pattern matching and
`_compute_rolling_vp_dynamic` computes them for any window `>= 1`, but
`resolve()` only did `_FIXED.get(name)`, returning `None`. This spec
therefore also closes the legacy asymmetry (ADR-6, INV-7) with a
surgical pattern-matching addition — leaving it unfixed would contradict
the spec's thesis and fail its own strengthened invariant test for
`vp_poc_10d`.

## Non-Goals

These are explicitly NOT being built in this spec:

- **New indicator math.** All 116 handlers exist and are tested. This
  spec is pure catalog wiring — no new calculations.
- **Cataloguing new metrics.** No new `MarketMetricDefinition` entries.
- **Full Composite refactor of `StrategyIndicatorCatalog`.** The legacy
  catalog remains the authority for period-parameterised indicators
  (`sma_50`, `atr_2`) and pattern-matched rolling-VP names
  (`vp_poc_10d`, `rvp_poc_48`, `cvp_vah_20d`). Only the registry-side
  usable-set rule is being promoted to a value object; the legacy
  catalog stays composed as-is. The ONE exception is a surgical
  pattern-matching addition to its `resolve()` (ADR-6) to close the
  same resolve/supports_concrete asymmetry for non-hardcoded rolling-VP
  windows — this is a consistency fix, not the excluded full merge.
  (A future spec may fully merge them.)
- **Making `UsableMetricSet` implement `IndicatorCapabilityProvider`.**
  It would force ISP violations (the set cannot meaningfully answer
  period/pattern questions). It is a focused collaborator, not a
  sub-catalog.
- **Changing the parser.** `StrategyIndicatorResolver` is correct — it
  honours whatever `resolve()` returns. No parser changes.
- **Loosening the handler-required gate.** Catalogued metrics WITHOUT a
  handler must still be rejected (Elliott Wave, VIX, turnover). This
  spec adds a regression test for that invariant.
- **Merging the `finbar/` mirror shims.** They re-export from the
  package; the fix propagates automatically.
