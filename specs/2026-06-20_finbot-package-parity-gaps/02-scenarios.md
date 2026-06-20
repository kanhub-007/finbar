# Scenarios — Finbot ⇄ Strategy Runtime Package Parity Gaps

Scenarios use Classical-school (Detroit), black-box tests: **real** domain
objects, **in-memory fakes** only at external boundaries (there are essentially
none here since the package is pure), and assertions on **outcomes** (returned
frames / trades / PnL), never on interactions. No `verify()` / `assert_called()`.

> **Model reminder (see `01-story.md`):** there is **no shared loop or
> simulator**. The package delivers **primitives** (enrichment, warmup-readiness,
> sizing, fill math). Each app keeps its own loop/driver. Parity comes from both
> loops calling the same primitives. "Replay" is finbot's integration test
> (fake data through the real live loop), not a use case and not a shared runner.

Slicing:

- **Slice 1 (Layer A):** `MultiTimeframeBarEnricher` + `RequiredDataValidator` — closes Gap #1.
- **Slice 2 (Layer B):** sizing + fill-model **primitives** (no runner) — closes Gap #2.

There is no Slice 3. (The earlier `replay()` facade is dropped: replay must
exercise finbot's real loop, not a shared one-liner.)

---

## Slice 1 — `MultiTimeframeBarEnricher` + `RequiredDataValidator` (Layer A)

### Scenario S1: Enricher produces the same merged frame as finbar's current backtest path
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the production strategy `14_amt_value_reject_30m_1h_mtf.yaml` parsed into a `StrategyDefinition` with `timeframes.primary=30min` and one informative `h1=1h`
  And the parser has produced `primary_required_indicators`, `informative_required_indicators["h1"]`, and `required_columns`
  And 5008 SOL 30min bars and 5005 SOL 1h bars are loaded from `finbar/data/finbar.db`
  When `MultiTimeframeBarEnricher.enrich(primary_bars, {"h1": info_bars}, definition, primary_req, info_req)` is called
  Then the returned DataFrame is column-for-column and value-for-value equal to the frame produced by the current `BacktestStrategyDefinitionUseCase._prepare_frame` + per-timeframe indicator jobs + feature calculator, on the same bars

**Input table:**
| Field | Type | Example | Constraints |
|---|---|---|---|
| primary_bars | list[dict] | SOL 30min OHLCV dicts | Non-empty, sorted ascending by timestamp |
| informative_bars | dict[str alias, list[dict]] | `{"h1": [1h bars]}` | One key per declared informative alias |
| definition | StrategyDefinition | parsed `14_amt_value_reject_30m_1h_mtf` | `.timeframes.has_informative()` is True |
| primary_required_indicators | list[str] | `["poc_slope_5", "above_value", "below_value"]` | From parser validation result |
| informative_required_indicators | dict[str alias, list[str]] | `{"h1": ["poc_slope_5", "above_value", "below_value"]}` | From parser validation result |

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| merged frame columns include `poc_slope_5`, `poc_slope_5_1h`, `above_value_1h`, `below_value_1h` | `assert "poc_slope_5_1h" in df.columns` |
| merged frame equals the reference frame from the current finbar path | `pd.testing.assert_frame_equal(df, reference, check_like=True)` |
| no lookahead: an informative value at primary row *t* reflects only 1h bars that **closed at or before** *t* | inspect alignment vs raw 1h close timestamps (no-lookahead property of `merge_timeframes`) |

**Verify (Classical school, black-box):**
```python
enricher = MultiTimeframeBarEnricher(
    indicator_calculator=PandasTaIndicatorCalculator(),
    bar_converter=PandasBarFrameConverter(),
    timeframe_merger=PandasTimeframeBarMerger(),
    feature_calculator=PandasStrategyFeatureCalculator(),
)
got = enricher.enrich(
    primary_bars=primary_bars,
    informative_bars={"h1": info_bars},
    definition=definition,
    primary_required_indicators=primary_req,
    informative_required_indicators={"h1": info_req},
)
# Reference produced by the CURRENT finbar orchestration (golden fixture
# captured before the refactor). The whole point: refactor must not move it.
pd.testing.assert_frame_equal(got, golden_reference_frame, check_like=True)
# Do NOT assert which internal methods were called.
```

**Also test:**
- Single-timeframe strategy (no informative) → enricher computes primary indicators + features only; no merge.
- Strategy with features but no informative → features still computed on the primary frame.
- Unknown/unsupported indicator name → raises `ValueError` with the indicator name in the message (mirrors `PandasTaIndicatorCalculator` today).
- Empty primary bars → raises `ValueError` (or returns empty frame, per parity with current path — pin whichever finbar does).

---

### Scenario S2: Finbar's backtest delegates to the enricher (refactor is behaviour-preserving)
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given `BacktestStrategyDefinitionUseCase` is constructed with a `MultiTimeframeBarEnricher`
  When it backtests the production MTF strategy over the SOL 30min+1h bars
  Then the backtest's trade list, equity curve, and summary metrics are byte-for-byte equal to the same backtest run on the pre-refactor code path

**Input table:**
| Field | Type | Example | Constraints |
|---|---|---|---|
| strategy | JSON/YAML definition | `14_amt_value_reject_30m_1h_mtf.yaml` | Validated MTF |
| execution | ExecutionConfig-ish request | 10% risk, 10x leverage, commission/slippage = 0 | From `BacktestStrategyDefinitionRequest` |

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| trades identical (entry/exit time+price, size, pnl) | deep-equal the trade dicts vs a golden backtest result |
| equity curve identical | `assert equity == golden_equity` |
| final summary metrics identical | compare the summary dict |

**Verify (Classical school, black-box):**
```python
use_case = create_backtest_strategy_definition_use_case()  # wired with enricher
result = use_case.execute(request)
# golden captured from the pre-refactor run over the same bars+config.
assert result.result.trades == golden_trades
assert _approx(result.result.final_value) == _approx(golden_final_value)
```

**Also test:**
- `run_strategy_pipeline` (the other backtest entry point that delegates to this use case) still produces identical results.
- A single-timeframe strategy backtest is unchanged (the enricher's no-informative branch must be a no-op relative to today).

---

### Scenario S3: The enricher is a pure package service — no finbar-the-app imports
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the package source tree under `packages/strategy-runtime/finbar_strategy_runtime/`
  When a static architecture check scans every module
  Then no module in `finbar_strategy_runtime` imports from `finbar.` (the app), `finbot`, Hyperliquid SDKs, SQLAlchemy, yfinance, or any I/O framework

**Input table:**
| Field | Type | Example | Constraints |
|---|---|---|---|
| scope | path | `packages/strategy-runtime/finbar_strategy_runtime/` | Package source only |

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| zero `from finbar.` / `import finbar` / `import finbot` in package | `grep -rn "import finbar\b\|from finbar\b\|import finbot\|hyperliquid\|sqlalchemy\|yfinance" packages/strategy-runtime/finbar_strategy_runtime/` returns nothing (excluding `.venv`) |

**Verify (Classical school, black-box):**
```python
# Architecture test: enforce the dependency-direction rule (ast-based scan
# in tests/test_package_purity.py).
assert _no_app_imports("finbar_strategy_runtime")
```

**Also test:**
- The enricher's only third-party import is `pandas` / `numpy` (already declared in `[pandas]` extra).

---

### Scenario S4: Enricher over a sliding warmup window matches the full-frame enrich (finbot streaming contract)
**Priority:** Should
**Slice:** 1

This is the property finbot's live `_enrich_bars` relies on: calling `enrich`
on the trimmed warmup window each candle must yield the **same latest row** as
enriching the full frame once.

**Gherkin:**
  Given the full enriched frame over all SOL bars
  When the last 500 primary bars + their 1h warmup are enriched separately via the enricher
  Then the final row of the windowed enrich equals the corresponding row of the full enrich (within float tolerance)

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| latest-row parity | compare the last row of `windowed` to `full.iloc[-1]` |
| column set identical | `assert set(windowed.columns) == set(full.columns)` |

**Verify:**
```python
full = enricher.enrich(all_primary, {"h1": all_info}, ...)
windowed = enricher.enrich(all_primary[-500:], {"h1": all_info[-N:]}, ...)
pd.testing.assert_series_equal(windowed.iloc[-1], full.iloc[-1], check_names=False)
```

**Also test:**
- Warmup window smaller than the longest indicator period → the relevant indicator column is NaN on early rows (warmup behaviour, not an error).

---

### Scenario S5: RequiredDataValidator computes the same warmup/first-tradable as finbar today
**Priority:** Must
**Slice:** 1

Finbot currently gates readiness on a fixed `min_bars=20` and **skips warmup
bars entirely** (never calling `on_bar`), so strategy state (crossovers, AMT
profiles) is cold on bar one. The fix is to share finbar's **data-driven**
warmup determination: the first row where all required columns are non-NaN.

**Gherkin:**
  Given an enriched frame and the strategy's `required_columns`
  When `RequiredDataValidator.validate(frame, required_columns)` is called
  Then it returns the same `warmup_bars`, `first_tradable`, `missing_after_warmup`, and `no_tradable_bars` as finbar's current `validate_required_data` on the same frame

**Input table:**
| Field | Type | Example | Constraints |
|---|---|---|---|
| frame | DataFrame | enriched output of S1 | Non-empty |
| required_columns | list[str] | `["poc_slope_5", "above_value_1h", ...]` | From parser |

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| `warmup_bars` == index of first row where all required cols are non-NaN | compare to a hand-computed expectation |
| output dict equals finbar's `validate_required_data` output | deep-equal |

**Verify:**
```python
v = RequiredDataValidator().validate(frame, required_columns)
assert v == golden_validate_required_data_output   # captured from finbar today
assert v["warmup_bars"] == first_row_where_all_nonan(frame, required_columns)
```

**Also test:**
- A required column that is never non-NaN → `no_tradable_bars=True`, column listed in `missing_after_warmup`.
- Empty `required_columns` → `warmup_bars=0` (everything tradable immediately).

> **Parity invariant (documented, not a package test — it is loop behaviour):**
> during warmup (rows before `first_tradable`), bars are fed to `on_bar()` for
> **state-building only**; no orders are generated. Finbar already does this
> (`_update_warmup_state`). Finbot must adopt the same rule using
> `RequiredDataValidator` instead of its fixed `min_bars` skip. This is a
> finbot-side change, validated end-to-end by the acceptance test below.

---

## Slice 2 — Sizing + fill-model primitives (Layer B)

> These scenarios cover the **primitives**, not a runner. The backtest loop
> stays in finbar; finbot's loop stays in finbot. Parity is proven by (a) the
> move being behaviour-preserving for finbar (S6), (b) the primitives being
> independently composable the way finbot's fake exchange needs (S7), and (c)
> the package staying pure (S8).

### Scenario S6: Finbar's backtest is unchanged after the primitives move into the package
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given the sizing + fill primitives (`PositionSizer`, `PositionOpener`, `PositionCloser`, `IntrabarExitResolver`, `MarginAccountManager`, `PositionExecutor`, `ExecutionConfig`, `LeverageConfig`, `SimulationState`, state entities, and the pure metric services) have been moved from finbar-the-app into `finbar_strategy_runtime.simulation`
  And finbar's `BacktestRunner` loop imports them from the package
  When the same backtest request runs before and after the move
  Then trade list, equity curve, and metrics are byte-for-byte identical

**Input table:**
| Field | Type | Example | Constraints |
|---|---|---|---|
| strategy | definition | production MTF | validated |
| execution | ExecutionConfig | 10% risk, 10x lev, margin_mode="full", enable_funding=… | frozen |

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| trades identical | deep-equal `result.trades == golden_trades` |
| equity curve identical | deep-equal |
| summary metrics identical | deep-equal |
| final_value identical within float tolerance | `abs(result.final_value - golden) < 1e-9` |

**Verify (Classical school, black-box):**
```python
runner = BacktestRunner()   # loop unchanged; imports primitives from package now
out = runner.run(df, strategy, initial_cash=10_000.0, risk_per_trade=0.10, ...)
assert out == golden_pre_move_result
```

**Also test:**
- Both backtest entry points (`run_backtest`, `BacktestStrategyDefinitionUseCase`, `run_strategy_pipeline`) produce identical results after the move.
- Liquidation path: a position breaching maintenance margin is closed with `exit_reason="margin_call"` (unchanged).
- Borrow/funding enabled: borrow + funding reduce cash as today (unchanged).
- Conservative entry: an entry signal on bar *t* fills at bar *t+1* open (loop semantics, unchanged).

---

### Scenario S7: Fill primitives are independently composable (finbot fake-exchange contract)
**Priority:** Must
**Slice:** 2

Finbot's **dry-run / replay** path does not run finbar's backtest loop; its fake
exchange gateway prices one fill at a time as bars arrive. The shared surface
must therefore expose the primitives composable in isolation, so the fake
exchange can reproduce the backtest's fill math.

**Gherkin:**
  Given a `PositionExecutor` constructed with an `ExecutionConfig` (10x leverage, full margin)
  And a `SimulationState` with initial cash 10_000
  When `executor.enter(state, entry, fill_price, date)` is called with a pending long entry whose stop defines a 10% risk distance
  Then the opened position size equals `(equity × risk_per_trade × leverage) / |entry−stop|` (the backtest formula), and cash/used_margin reflect slippage+commission
  And given a later bar whose low breaches the stop, `executor.check_exit_conditions(state, open, high, low, date)` triggers a stop fill, and `exit_position` produces a `TradeRecord` whose gross/net PnL are consistent with the entry

**Input table:**
| Field | Type | Example | Constraints |
|---|---|---|---|
| entry | PendingEntry | direction="long", stop_price=90, signal_close=100 | stop on the correct side of price |
| fill_price | float | 100.0 | > 0 |
| execution_config | ExecutionConfig | leverage=10, commission=0, slippage=0, margin_mode="full" | frozen |

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| size matches the sizer formula | `assert abs(state.position.size - expected) < 1e-6` |
| commission + slippage applied | inspect `state.total_commission`, `state.total_slippage` |
| margin booked (full-margin mode) | inspect `state.used_margin` |
| stop fill price is gap-aware (clamped to bar range) | inspect the exit price after `check_exit_conditions` |
| resulting TradeRecord PnL is internally consistent | `net == gross - entry_commission - exit_commission - borrow` |

**Verify:**
```python
executor = PositionExecutor(ExecutionConfig(leverage_multiplier=10.0, margin_mode="full"))
state = SimulationState(initial_cash=10_000.0)
executor.setup_full_margin(10_000.0)
executor.enter(state, entry, price=100.0, date="2026-04-01T00:00:00")
expected = (10_000.0 * 0.10 * 10.0) / abs(100.0 - 90.0)   # equity*risk*lev / risk_dist
assert abs(state.position.size - expected) < 1e-6

# Later bar breaches the stop:
executor.check_exit_conditions(state, open_price=99.0, high=99.5, low=88.0,
                               bar_date="2026-04-01T00:30:00")
trade = state.trades[-1]
assert trade["exit_reason"].startswith("stop") or trade["exit_reason"] == "take_profit"
assert _pnl_consistent(trade)
```

**Also test:**
- Zero-size entry (stop invalid / unaffordable) is rejected via diagnostics, not an exception.
- `liquidate_open` closes any remaining position at a given price (used at end-of-run / session end).

> **Fill-timing parity contract (documented invariant, enforced by the
> acceptance test):** for replay PnL to match the backtest, finbot's fake
> exchange must replicate the backtest's per-bar timing — entries fill at
> **next-bar open**, exits are **intrabar gap-aware** (stop/target clamped to
> bar high/low). The shared *primitives* guarantee the fill **math**; the
> *timing* is each loop's responsibility and is verified end-to-end by the
> replay test. There is deliberately no shared loop enforcing it.

---

### Scenario S8: The simulation subpackage imports nothing from finbar-the-app
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given the new `finbar_strategy_runtime.simulation` subpackage
  When an architecture scan runs
  Then it imports only from the package itself, stdlib, pandas/numpy — never from `finbar.` / `finbot` / Hyperliquid / SQLAlchemy / yfinance

**Verify:**
```python
# Same architecture-scan pattern as S3, scoped to .../simulation/.
assert _no_app_imports("finbar_strategy_runtime.simulation")
```

**Also test:**
- Moving the entities (`ExecutionConfig`, `LeverageConfig`, `PendingEntry`, `PendingExit`, `BacktestDiagnostic`, `TradeRecord`, `MarginAccount`) into the package leaves no dangling `from finbar.core.domain.entities...` imports in finbar-the-app (compat re-exports or alias updates cover remaining callers).

---

## Acceptance criteria — the parity test (lives in finbot)

This is the end-to-end proof. It is implemented in **finbot** and depends on
Slices 1 & 2 landing in the package.

- Replay SOL 30min + 1h (`finbar/data/finbar.db`, 2026-03-05 → 2026-06-17)
  through **Finbot's real live pipeline** (`LiveTradingRuntimeUseCase.process_closed_candle`),
  mocking **only** the Hyperliquid websocket boundary (the data stream) and the
  exchange gateway.
- Enrichment flows through the shared `MultiTimeframeBarEnricher` (Slice 1);
  readiness is gated by the shared `RequiredDataValidator` (Slice 1), and warmup
  bars are fed to `on_bar` for state-building.
- Order **sizing** uses the shared `PositionSizer` via `ExecutionConfig`/
  `LeverageConfig` (Slice 2) — no more fixed `0.001`.
- The **fake exchange** (dry-run/replay submission strategy) prices fills using
  the shared `PositionExecutor` / `IntrabarExitResolver` / `PositionCloser`
  (Slice 2), replicating the backtest's next-bar-open entry and intrabar
  gap-aware exits.
- The **live** path is unchanged in spirit: it still submits to Hyperliquid and
  uses real exchange fills (no shadow bookkeeping). Live is **not** asserted to
  match the backtest exactly — only replay is.
- Strategy `14_amt_value_reject_30m_1h_mtf.yaml`, **10% risk / 10x leverage**.
- Assert: number of trades, entry/exit times and prices, and total realized PnL
  match the Finbar backtest of the same config (exact, because decisions,
  sizing, **and** the fill math are shared primitives; the only thing finbot
  contributes is feeding the bars, which is just data).

**Why exact is achievable on the replay path:** finbot's real loop drives the
*same* enrichment, sizing, and fill primitives as the backtest, through a fake
exchange that uses the *same* fill math. The loop/driver and venue differ, but
every value that affects a trade is computed by shared code.
