# Implementation Guide — Finbot ⇄ Strategy Runtime Package Parity Gaps

Ordered by slice. Within each slice, capture a **golden reference** *before*
changing behaviour, then refactor until the golden test passes again. This is
the safety rail for a behaviour-preserving extraction.

> **No runner extraction.** The backtest loop (`_run_loop`) stays in finbar's
> `BacktestRunner`. Slice 2 moves only the **primitives** and changes import
> paths; the loop body is untouched. (See `05-architecture.md` ADR-11.)

Conventions:
- One class per file (AGENTS.md). New modules mirror the one-class-per-file rule.
- Absolute imports. ORM/domain aliases where needed (`DomainX`/`OrmX`).
- `ruff check` + `black` clean before each step's Verify.

---

# Slice 1 — `MultiTimeframeBarEnricher` + `RequiredDataValidator` (Layer A)

## Step 1.0: Capture the golden reference frame + warmup diagnostics
**File:** `packages/strategy-runtime/tests/test_multi_timeframe_bar_enricher.py` (new; run against the *old* path first)

Before writing the enricher, capture what the current finbar path produces.

```python
# Fixture: load SOL 30min + 1h bars from finbar/data/finbar.db (table price_bar).
# Parse the production strategy via the package parser to get definition + the
# per-timeframe required-indicator split.
definition, primary_req, info_req, required_cols = _parse_mtf_strategy(...)
# Reference: drive the CURRENT finbar orchestration (per-TF indicator jobs +
# _prepare_frame + features) over these bars, plus validate_required_data.
golden_frame = _current_finbar_merged_frame(definition, primary_bars, info_bars, ...)
golden_warmup = _current_finbar_validate_required_data(golden_frame, required_cols)
# Persist both to committed fixtures (parquet / json) so tests are hermetic.
```

**Verify:** the golden-capture script runs and writes the fixtures.
**Common mistake:** don't compute the reference *inside* the test from the new
enricher — that's circular. Capture from the old path.

---

## Step 1.1: Create the enricher in the package
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/multi_timeframe_bar_enricher.py`

Implement `MultiTimeframeBarEnricher.enrich()` per `03-domain.md`. Body is a
pipeline (extract method; keep `enrich` < 30 lines):

```python
def enrich(self, primary_bars, informative_bars, definition,
           primary_required_indicators, informative_required_indicators):
    primary = self._frame_and_compute(primary_bars, primary_required_indicators)
    timeframes = definition.timeframes
    if timeframes is None or not timeframes.has_informative():
        self._check_no_informative_supplied(informative_bars)
        return self._features(primary, definition)
    frame = primary
    for item in timeframes.informative:                 # InformativeTimeframe
        info = self._frame_and_compute(
            self._bars_for_alias(informative_bars, item),
            informative_required_indicators.get(item.alias, []),
        )
        frame = self._timeframe_merger.merge(frame, info, item.interval)
    return self._features(frame, definition)
```

Reuse the existing `PandasTaIndicatorCalculator`, `PandasBarFrameConverter`,
`PandasTimeframeBarMerger`, `PandasStrategyFeatureCalculator` — do **not**
reimplement indicator math or merge logic.

**Verify:** `ruff check && pytest test_multi_timeframe_bar_enricher.py` — S1 passes.
**Common mistake:** computing features *before* the merge. Features may reference
informative columns (`*_1h`), so they must run **after** the merge — same order
as today's `_prepare_frame`.

---

## Step 1.2: Create `RequiredDataValidator`
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/required_data_validator.py`

Move the body of finbar's pure `validate_required_data(frame, required_columns)`
into `RequiredDataValidator.validate(...)`. Behaviour identical.

**Verify:** S5 passes — output equals `golden_warmup`.
**Common mistake:** changing the returned dict keys; finbar's callers read
`warmup_bars`, `first_tradable`, `missing_after_warmup`, `no_tradable_bars`.
Keep them.

---

## Step 1.3: Add the package purity test
**File:** `packages/strategy-runtime/tests/test_package_purity.py` (new or extend)

S3: ast-based scan of the package source (excluding `.venv`) for `from finbar`,
`import finbar`, `import finbot`, `hyperliquid`, `sqlalchemy`, `yfinance`. Empty.

**Verify:** `pytest -k purity` passes.

---

## Step 1.4: Refactor finbar's backtest to use the enricher + validator
**File:** `finbar/core/application/use_cases/backtest_strategy_definition.py`

Replace the body of `_prepare_frame` + the feature step in
`_resolve_and_compute_signals` with a single call to the injected
`MultiTimeframeBarEnricher`. Replace the `validate_required_data(...)` call with
`RequiredDataValidator(...).validate(...)`. Add both as constructor deps; the
DI factory wires them with the pandas implementations.

Keep validation, error mapping, and missing-column checks exactly where they are.

```python
frame = self._enricher.enrich(
    primary_bars=request.bars,
    informative_bars=request.informative_bars or {},
    definition=validation.definition,
    primary_required_indicators=validation.primary_required_indicators,
    informative_required_indicators=validation.informative_required_indicators,
)
warmup = self._data_validator.validate(frame, validation.required_columns)
```

**Verify:** S2 passes — finbar backtest trades/equity/metrics equal the golden
captured pre-refactor, over the production SOL strategy at 10% risk / 10x lev.
**Common mistake:** dropping the `_validate_informative_payload_shape` /
`_select_informative_bars` error semantics. Push those checks into the enricher
(or keep a thin pre-check) so error messages/codes don't change.

---

## Step 1.5: Bump the package version
**Files:** `packages/strategy-runtime/pyproject.toml`, `.../finbar_strategy_runtime/__init__.py`

- `version = "0.2.0"` (pyproject), `__version__ = "0.2.0"` (`__init__.py`).

**Verify:** `python -m build` succeeds; wheel installs.
**Common mistake:** bumping only one of the two version strings.

---

## Step 1.6: Finbot consumes Slice 1
**Repo:** finbot (`C:\HAL\Github\finbot`)
**Files:** `finbot/pyproject.toml`, `live_trading_runtime.py`,
`shared_runtime_indicator_calculator.py` (or a new enricher adapter),
`runtime_factory.py`

- Bump pin: `finbar-strategy-runtime[pandas,yaml]>=0.2.0,<0.3.0`.
- `_enrich_bars()`: assemble primary + per-informative warmup windows, call the
  shared `MultiTimeframeBarEnricher.enrich(...)` over the trimmed window.
- `process_informative_candle()` already fills `_informative_cache`; wire the
  cache into the enricher (it was dead state before).
- `runtime_factory.py`: retain the informative warmup fetch (currently discarded
  at ~line 141) and pass it to the runtime.
- Gate readiness via `RequiredDataValidator` (data-driven), not `min_bars`.
- **Adopt the warmup-state rule:** during warmup (rows before `first_tradable`),
  call `on_bar()` for state-building and suppress order generation. (Finbot
  currently skips warmup entirely → cold strategy state on bar one.)

(Detailed finbot wiring is owned by finbot's own MTF spec
`finbot/specs/2026-06-20_multi-timeframe-support/`.)

**Verify:** the finbot replay harness produces non-zero signals for the
production MTF strategy (Gap #1 symptom — `Unknown indicator 'poc_slope_5_1h'` —
is gone). Full PnL parity requires Slice 2.

---

# Slice 2 — Sizing + fill-model primitives (Layer B)

> **ADR-6 and ADR-11 must be agreed before starting this slice** (see
> `05-architecture.md`). ADR-6 amends ADR-2 to admit the deterministic fill
> primitives; ADR-11 fixes "no shared loop."

## Step 2.0: Capture golden backtest results
**File:** `packages/strategy-runtime/tests/test_fill_primitives_parity.py` (new; run against old path first)

Capture golden backtest output (trades, equity curve, summary metrics,
final_value) for:
- the production SOL strategy at 10% risk / 10x leverage, and
- at least one single-TF strategy (regression guard), and
- at least one config exercising liquidation + borrow/funding.

Drive the *current* `BacktestRunner.run()` to produce these; commit as fixtures.

**Verify:** golden fixtures captured and committed.
**Common mistake:** not covering the margin-call / funding paths — those are the
easiest to silently break during a move.

---

## Step 2.1: Move the primitives into the package
**Move** (git mv, preserving history) the files listed in `03-domain.md` from
`finbar/infrastructure/services/` and `finbar/core/domain/entities/` and
`finbar/core/domain/services/` into
`packages/strategy-runtime/finbar_strategy_runtime/simulation/`.

Adjust imports inside the moved files:
- `from finbar.core.domain.entities.execution_config import ExecutionConfig`
  → `from finbar_strategy_runtime.simulation.execution_config import ExecutionConfig`.
- `from finbar.core.domain.services.annualization import ...`
  → `from finbar_strategy_runtime.simulation.metrics.annualization import ...`.
- `from finbar.infrastructure.services.backtest_position import BacktestPosition`
  → `from finbar_strategy_runtime.simulation.simulated_position import SimulatedPosition` (renamed on move).

Rename on move: `BacktestLoopState` → `SimulationState` (file
`simulation_state.py`), `BacktestPosition` → `SimulatedPosition` (file
`simulated_position.py`). Update all references.

Leave **compatibility re-exports** at the old finbar paths so callers compile:

```python
# finbar/core/domain/entities/execution_config.py  (compat shim)
from finbar_strategy_runtime.simulation.execution_config import (  # noqa: F401
    ExecutionConfig,
)
```

**Do NOT move `backtest_runner.py` or `backtest_result_builder.py`** — they are
finbar's loop and result assembly. Only their imports change.

**Verify:** `ruff check finbar/ packages/strategy-runtime/` clean; finbar's
existing backtest tests still pass (unchanged behaviour — it's a move + rename).
**Common mistake:** forgetting a re-export. Grep:
`grep -rn "BacktestLoopState\|BacktestPosition\|from finbar.core.domain.entities.\(execution_config\|leverage_config\|pending_entry\|pending_exit\|backtest_diagnostic\|trade_record\|margin_account\)" finbar/`.

---

## Step 2.2: Rewire finbar's `BacktestRunner` imports
**File:** `finbar/infrastructure/services/backtest_runner.py`

The loop logic (`_run_loop`, `_execute_pending`, `_process_signal`, etc.) is
**unchanged**. Only imports change: pull `PositionExecutor`, `SimulationState`,
`ExecutionConfig`, `PendingEntry`, `PendingExit` from
`finbar_strategy_runtime.simulation`. `_execution_config_from_params` stays
(this is finbar's param-parsing, app-specific).

```python
from finbar_strategy_runtime.simulation.execution_config import ExecutionConfig
from finbar_strategy_runtime.simulation.pending_entry import PendingEntry
from finbar_strategy_runtime.simulation.pending_exit import PendingExit
from finbar_strategy_runtime.simulation.position_executor import PositionExecutor
from finbar_strategy_runtime.simulation.simulation_state import SimulationState
```

**Verify:** S6 passes — `BacktestRunner.run()` output equals the golden from
Step 2.0, byte-for-byte. Both backtest entry points agree.

---

## Step 2.3: Package purity test for the simulation subpackage
**File:** `packages/strategy-runtime/tests/test_package_purity.py` (extend)

S8: scope the architecture scan to `.../simulation/` too. Imports must be
package-internal + pandas/numpy only.

**Verify:** `pytest -k purity` passes.

---

## Step 2.4: Bump version
**Files:** `pyproject.toml`, `__init__.py`

- `version = "0.3.0"`, `__version__ = "0.3.0"`.

**Verify:** build + install succeed.

---

## Step 2.5: Finbot consumes Slice 2
**Repo:** finbot
**Files:** `finbot/pyproject.toml`, dry-run/replay submission strategy, `order_planner.py`

- Bump pin: `finbar-strategy-runtime[pandas,yaml]>=0.3.0,<0.4.0`.
- **Dry-run / replay path:** the fake exchange / dry-run submission strategy
  prices fills via the shared `PositionExecutor` / `IntrabarExitResolver` /
  `PositionCloser`. Replicate backtest timing: entries fill at **next-bar open**,
  exits are **intrabar gap-aware** (stop/target clamped to bar high/low).
- **Order sizing:** use the shared `PositionSizer` (via `ExecutionConfig`/
  `LeverageConfig`) for dry-run/replay — no more fixed `0.001`. Live sizing may
  also use it (sizing is a shared decision primitive).
- **Live path:** unchanged — `OrderPlanner` + `LiveSubmissionStrategy` stay
  (Layer C). Real exchange fills; no shadow bookkeeping.

**Verify:** the parity test (Acceptance criteria in `02-scenarios.md`) passes —
trades and realized PnL match the finbar backtest within tolerance (exact,
because decisions, sizing, and fill math are shared primitives).

---

## After both slices: full review

Run the complete review suite per AGENTS.md §6, scoped to the changed code:

- `/review_quality` — architecture (layer imports), patterns (Pipeline on
  `enrich`, Facade on `PositionExecutor`), SOLID, DRY.
- `/review_logic` — the move must not change fill/PnL math; focus on
  warmup/entry-timing/liquidation edge cases.
- `/review_security` — mostly N/A (pure package); confirm no secrets/keys added.
- `/review_performance` — the enricher is `O(window)` per candle (finbot
  streaming); confirm `max_length` bounding is preserved.
- `/review_tests` — golden-frame + golden-result parity tests cover the
  behaviour-preserving claim; edge cases per scenarios.
- `/review_spec` — implemented code vs this spec.

Then: pin the package versions in both repos, tag the releases, and run the
finbot parity test end-to-end.
