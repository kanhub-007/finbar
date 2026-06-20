# Domain Model — Finbot ⇄ Strategy Runtime Package Parity Gaps

This spec adds **pure primitive services** to the `finbar_strategy_runtime`
package (Layers A and B of the three-layer model) and turns finbar-the-app's
duplicated logic into thin callers of those primitives.

> **No runner, no loop, no `SimulationResult`.** The package does **not** gain a
> `StrategySimulator`, a `run()` over a frame, or a `replay()` facade. The
> backtest loop stays in finbar; finbot's loop stays in finbot. The package
> delivers the **functions/classes** both loops call. (See `05-architecture.md`
> ADR-11.) Layer C (venue) is untouched and stays in finbot.

All new code is **pure**: no I/O, no Hyperliquid/SDK, no persistence, no async.
Third-party surface stays `pandas` / `numpy` only.

---

## Slice 1 — `MultiTimeframeBarEnricher` + `RequiredDataValidator` (Layer A)

### New modules

```
packages/strategy-runtime/finbar_strategy_runtime/indicators/
  multi_timeframe_bar_enricher.py   ← NEW
  required_data_validator.py        ← NEW
```

### `MultiTimeframeBarEnricher`

A pure service that turns `(primary bars + informative bars + definition +
per-timeframe required indicators)` into the fully merged, indicator-enriched
DataFrame that `on_bar()` consumes. It folds together the two orchestrations
that today live split in finbar-the-app:

1. **Per-timeframe indicator computation** (today: `ComputeStrategyIndicatorsUseCase`
   starts one indicator job per timeframe).
2. **Merge + features** (today: `BacktestStrategyDefinitionUseCase._prepare_frame`).

```python
class MultiTimeframeBarEnricher:
    """Frame each timeframe, compute its indicators, merge, then run features.

    Pure service. The merge uses no-lookahead as-of alignment with
    interval_offset (already guaranteed by ``merge_timeframes``), so feeding
    the closed-bar warmup window yields correct values even in streaming.

    The caller supplies the per-timeframe indicator split (parser output),
    not re-derived here.
    """

    def __init__(
        self,
        indicator_calculator: IndicatorCalculator,    # PandasTaIndicatorCalculator
        bar_converter: BarFrameConverter,             # PandasBarFrameConverter
        timeframe_merger: TimeframeBarMerger,         # PandasTimeframeBarMerger
        feature_calculator: StrategyFeatureCalculator | None = None,
    ) -> None: ...

    def enrich(
        self,
        primary_bars: list[dict],
        informative_bars: dict[str, list[dict]],     # alias -> bars
        definition: StrategyDefinition,
        primary_required_indicators: list[str],
        informative_required_indicators: dict[str, list[str]],
    ) -> "pd.DataFrame":
        """
        1. frame primary_bars; compute primary_required_indicators on it
        2. for each informative alias in definition.timeframes.informative:
             frame informative_bars[alias];
             compute informative_required_indicators[alias] on it
        3. merge each informative into the primary frame via timeframe_merger
           (produces *_<interval> suffixed columns, e.g. poc_slope_5_1h)
        4. if feature_calculator and definition.features: compute features
           on the merged frame
        5. return the merged enriched frame
        """
        ...
```

### `RequiredDataValidator`

Wraps finbar's current pure function `validate_required_data(frame,
required_columns)` (data-driven warmup: the first row where all required columns
are non-NaN). Shared so finbot stops gating on a fixed `min_bars` and stops
skipping warmup bars entirely.

```python
class RequiredDataValidator:
    """Data-driven warmup/readiness for an enriched frame.

    Returns warmup_bars, first_tradable, missing_after_warmup, no_tradable_bars
    — identical to finbar's current ``validate_required_data``.
    """

    def validate(
        self,
        frame: "pd.DataFrame",
        required_columns: list[str],
    ) -> dict: ...
```

### Existing interfaces `MultiTimeframeBarEnricher` composes (no changes)

| Interface | File (package) | Today's impl |
|---|---|---|
| `IndicatorCalculator.calculate(df, indicators) -> df` | `domain/interfaces/indicator_calculator.py` | `PandasTaIndicatorCalculator` |
| `BarFrameConverter.bars_to_frame / frame_to_bars` | `domain/interfaces/bar_frame_converter.py` | `PandasBarFrameConverter` |
| `TimeframeBarMerger.merge(primary, informative, interval, columns=None)` | `domain/interfaces/timeframe_bar_merger.py` | `PandasTimeframeBarMerger` |
| `StrategyFeatureCalculator.calculate(frame, features)` | `domain/interfaces/strategy_feature_calculator.py` | `PandasStrategyFeatureCalculator` |

### Existing entities consumed (no changes)

| Entity | Source (package) | Used for |
|---|---|---|
| `StrategyDefinition` | `domain/entities/strategy_definition.py` | `.timeframes`, `.features` |
| `TimeframeDeclaration` | `domain/entities/timeframe_declaration.py` | `.primary`, `.informative`, `.has_informative()` |
| `InformativeTimeframe` | `domain/entities/informative_timeframe.py` | `.alias`, `.interval` |

### Finbar-the-app changes

| File | Change |
|---|---|
| `finbar/core/application/use_cases/backtest_strategy_definition.py` | `_prepare_frame` + the feature step delegate to `MultiTimeframeBarEnricher.enrich(...)`. The warmup call delegates to `RequiredDataValidator`. Validation, error mapping, and the backtest call stay. |
| `finbar/core/application/use_cases/compute_strategy_indicators.py` | Unchanged in behaviour (it dispatches async jobs — app-specific). Its per-TF indicator split is now also embodied by the enricher for the synchronous path. No deletion. |

### Finbot changes (consumer)

| File | Change |
|---|---|
| `live_trading_runtime.py` | `_enrich_bars()` builds primary + informative warmup windows and calls the shared enricher over the trimmed window each candle. `_informative_cache` (populated by `process_informative_candle`) now feeds the enricher instead of being dead state. Readiness gated by `RequiredDataValidator` (data-driven), not `min_bars`. **Warmup bars are fed to `on_bar` for state-building; trading suppressed until `first_tradable`** (finbot currently skips warmup entirely → cold strategy state). |
| `shared_runtime_indicator_calculator.py` | Widened to an enricher adapter, or replaced by a new `SharedRuntimeMultiTimeframeEnricher` delegating to the package. |
| `runtime_factory.py` | The currently-discarded informative warmup fetch (`info_bars` at ~line 141) is retained and passed to the runtime so the enricher has informative history. |

---

## Slice 2 — Sizing + fill-model primitives (Layer B)

Move finbar-the-app's execution layer into the package as a new `simulation`
subpackage. **Primitives only — no loop, no runner.** Two kinds of consumer:

1. **Finbar's `BacktestRunner` loop** — imports the primitives and drives them
   per bar (unchanged loop logic, changed import paths).
2. **Finbot's fake exchange / dry-run submission** — composes the fill
   primitives to price one fill at a time as bars arrive (live does **not** use
   these — it uses real exchange fills).

### New subpackage layout

```
packages/strategy-runtime/finbar_strategy_runtime/simulation/   ← NEW
  __init__.py
  execution_config.py              ← moved from finbar core domain entities
  leverage_config.py               ← moved
  pending_entry.py                 ← moved
  pending_exit.py                  ← moved
  backtest_diagnostic.py           ← moved
  trade_record.py                  ← moved
  margin_account.py                ← moved
  position_sizer.py                ← moved from finbar infra services
  position_opener.py               ← moved
  position_closer.py               ← moved
  intrabar_exit_resolver.py        ← moved
  margin_account_manager.py        ← moved
  position_executor.py             ← moved (per-bar facade; NO loop)
  simulation_state.py              ← moved (was BacktestLoopState)
  simulated_position.py            ← moved (was BacktestPosition)
  metrics/
    annualization.py               ← moved (pure)
    backtest_metrics.py            ← moved (pure)
    rolling_metrics.py             ← moved (pure)
```

> Naming: `BacktestRunner` is **not** moved (it is finbar's loop/driver — stays
> in finbar, imports primitives from the package). The two state classes are
> renamed on move because finbot imports them and the `Backtest` prefix is
> misleading in a shared library: `BacktestLoopState` → `SimulationState`,
> `BacktestPosition` → `SimulatedPosition`. All other classes keep their names
> to minimize churn.

### What the package exposes (primitives)

| Primitive | Role | Backtest uses | Finbot live uses | Finbot dry-run/replay uses |
|---|---|:-:|:-:|:-:|
| `ExecutionConfig` | commission/slippage/leverage/margin knobs (frozen value object) | ✅ | ✅ | ✅ |
| `LeverageConfig` | liquidation price, stop-vs-liq validation | ✅ | ✅ (risk gates) | ✅ |
| `PositionSizer` | `size = equity·risk·lev / \|entry−stop\|` | ✅ | ✅ | ✅ |
| `PositionOpener` | entry validation + position creation | ✅ | ❌ | ✅ |
| `PositionCloser` | exit settlement, gross/net PnL, commission, borrow | ✅ | ❌ | ✅ |
| `IntrabarExitResolver` | gap-aware stop/target on bar H/L | ✅ | ❌ | ✅ |
| `MarginAccountManager` | margin booking, liquidation, funding | ✅ | ❌ | ✅ |
| `PositionExecutor` | per-bar facade composing the above (enter/exit/check/liquidate) | ✅ | ❌ | ✅ |
| `SimulationState` / `SimulatedPosition` | run state book (cash, position, trades, equity_curve) | ✅ | ❌ | ✅ |
| `TradeRecord` | trade shape | ✅ | ❌ | ✅ |
| `PendingEntry` / `PendingExit` | queued signal carriers | ✅ | ❌ | ✅ |
| `metrics/*` | sharpe/sortino/calmar/annualization (pure) | ✅ | optional | ✅ (to compare) |

`PositionExecutor` is a **per-bar facade**, not a loop. It exposes
`enter(state, entry, price, date)`, `exit_position(...)`,
`check_exit_conditions(state, open, high, low, date)`, `liquidate_open(...)`.
The decision of *when* and *in what order* to call these per bar belongs to
each app's loop.

### Existing interface consumed (no changes)

| Interface | File (package) | Note |
|---|---|---|
| `TradingStrategy.on_bar(bar, position) -> SignalResult` | `domain/interfaces/trading_strategy.py` | Already shared. Untouched. |

### Finbar-the-app changes

| File | Change |
|---|---|
| `finbar/infrastructure/services/backtest_runner.py` | **Stays.** The loop logic is unchanged; only its imports change to pull `PositionExecutor`, `SimulationState`, `ExecutionConfig`, etc. from `finbar_strategy_runtime.simulation`. It still implements finbar's `BacktestEngine` ABC. |
| `finbar/infrastructure/services/position_executor.py` (+ sizer/opener/closer/resolver/margin/state/position) | **Deleted** — moved into the package. |
| `finbar/infrastructure/services/backtest_result_builder.py` | **Stays** (finbar-specific result assembly); its import of the metric services changes to `finbar_strategy_runtime.simulation.metrics`. |
| `finbar/core/domain/services/annualization.py`, `backtest_metrics.py`, `rolling_metrics.py` | **Moved** into `.../simulation/metrics/`. Old paths re-export for compatibility if other finbar code uses them. |
| `finbar/core/domain/entities/{execution_config,leverage_config,pending_entry,pending_exit,backtest_diagnostic,trade_record,margin_account}.py` | **Moved** into `.../simulation/`. Old paths keep compat re-exports so callers compile in the same slice: `from finbar_strategy_runtime.simulation.execution_config import ExecutionConfig  # noqa: F401`. |

### Finbot changes (consumer)

| File | Change |
|---|---|
| `dry_run_submission_strategy.py` (and/or a replay fake-exchange adapter) | Price fills via the shared `PositionExecutor` / `IntrabarExitResolver` / `PositionCloser` instead of synthesizing fills at `close` with fee=0. Replicate backtest timing: entries at next-bar-open, exits intrabar gap-aware. |
| `order_planner.py` | **Live path only** — unchanged in role. Sizing for dry-run/replay is delegated to the shared `PositionSizer` so it matches the backtest. Live sizing may also use the shared sizer (decision/sizing primitives are shared with live), but live **fills** remain the exchange's. |

### Entity vs ORM separation check

None of the moved classes are ORM/persistence models — they are pure dataclasses
and pure services. (`trade_record.py` is a dataclass, not an ORM model.) Any
persisted trade row in finbar is a separate `OrmTrade` mapped via a mapper,
which is finbar-the-app's concern and does not move.

---

## Domain events

None. The primitives are synchronous and pure; they return values / mutate the
passed `SimulationState`. Cross-cutting concerns (logging, metrics emission)
stay as decorators inside the apps, not in the package.

---

## Interfaces (for DI) — summary of the net change

| Surface | Owner before | Owner after | Type |
|---|---|---|---|
| `MultiTimeframeBarEnricher` | — | package | concrete service (composes existing ABCs) |
| `RequiredDataValidator` | — | package | concrete service |
| `PositionSizer` / `Opener` / `Closer` / `IntrabarExitResolver` / `MarginAccountManager` / `PositionExecutor` | finbar | package | concrete services |
| `ExecutionConfig` / `LeverageConfig` / `TradeRecord` / `PendingEntry` / `PendingExit` / `SimulationState` / `SimulatedPosition` | finbar | package | value objects / state |
| `BacktestEngine` (finbar ABC) | finbar | finbar (unchanged) | ABC — `BacktestRunner` still implements it |

`MultiTimeframeBarEnricher`, `RequiredDataValidator`, and the simulation
primitives are intentionally **concrete classes, not ABCs**: there is one
correct pure implementation (pandas). If a second backend ever appears (e.g. a
streaming engine), an ABC can be extracted later — YAGNI for now. The
collaborators the enricher composes (`IndicatorCalculator`, `TimeframeBarMerger`,
etc.) remain ABCs because those *do* have multiple backends (pandas vs streaming).

---

## Dependency footprint (why this move is safe)

The execution layer is self-contained. Its imports today are:
- **pandas/numpy** — only `backtest_runner.py` (the loop) uses pandas directly; the loop stays in finbar, so the package's pandas use is limited to the metric services and the validator.
- **package** — `TradingStrategy` (already shared).
- **finbar entities / pure metric services** — the ones being moved.

No imports of: SQLAlchemy, yfinance, Hyperliquid, FastAPI/MCP, repositories,
fetchers, job managers, presentation. Moving the primitives introduces **zero**
new third-party dependencies and **zero** app coupling. (ADR-2's real intent —
"no venue/exchange plumbing in the package" — is preserved.)
