# Implementation Guide — Backtest Trust and Leverage Correctness

Follow Red → Green → Refactor per scenario. Use real objects and in-memory fakes; do not mock domain objects or assert private calls.

---

## Step 1: Fix informative timeframe job intervals
**File:** `finbar/core/application/use_cases/compute_strategy_indicators.py`

Replace alias-string handling with an alias-to-interval lookup. `validation.informative_required_indicators` is keyed by alias strings, not `InformativeTimeframe` objects.

Expected shape:
```python
alias_to_interval = dict(validation.timeframe_intervals)
...
for alias, indicators in validation.informative_required_indicators.items():
    interval = alias_to_interval.get(alias)
    if interval is None:
        # Should not happen after parser validation; return validation-style error
    inputs.append(_IndicatorInput(..., interval=interval, timeframe_alias=alias))
```

**Verify:**
```bash
.venv/Scripts/python -m pytest tests/test_application/test_strategy_json_multi_timeframe.py -q
```

**Common mistake:** Falling back to `1h` for alias strings. Fallbacks hide parser/use-case drift.

---

## Step 2: Keep strategy state warm during warmup while blocking trades
**Files:**
- `finbar/core/application/use_cases/backtest_strategy_definition.py`
- `finbar/infrastructure/services/backtest_runner.py`
- `finbar/infrastructure/services/backtest_loop_state.py` if state needs warmup metadata

Do not slice warmup bars away before engine execution. Pass a `first_tradable_index` or equivalent into `BacktestRunner.run`. The runner should call `strategy.on_bar()` on warmup bars to update crossover state, but must not create pending entries, execute pending entries, or emit trades before the first tradable bar.

Suggested params:
```python
first_tradable_index=int(warmup["warmup_bars"])
warmup_bars=int(warmup["warmup_bars"])
first_tradable=warmup["first_tradable"]
```

**Verify:**
```bash
.venv/Scripts/python -m pytest tests/test_infrastructure/test_backtest_edge_cases.py tests/test_application/test_strategy_json_multi_timeframe.py -q
```

**Common mistake:** Pre-feeding warmup bars outside the engine. That splits state progression across layers and makes behaviour harder to trust.

---

## Step 3: Add maintenance-aware liquidation
**Files:**
- `finbar/core/domain/entities/leverage_config.py`
- `finbar/core/domain/entities/execution_config.py`
- `finbar/infrastructure/services/position_opener.py`
- `finbar/infrastructure/services/position_closer.py`
- `finbar/infrastructure/services/margin_account_manager.py`
- `finbar/infrastructure/services/backtest_result_builder.py`

Add `maintenance_margin_pct` to the liquidation calculation input. A conservative isolated-margin approximation:

```python
initial_margin_fraction = 1.0 / leverage
if long:
    liq = entry_price * (1.0 - initial_margin_fraction + maintenance_margin_pct)
if short:
    liq = entry_price * (1.0 + initial_margin_fraction - maintenance_margin_pct)
```

Guard invalid settings:
- leverage <= 1: no liquidation / spot semantics
- maintenance < 0: reject/diagnose
- maintenance >= initial margin fraction: reject/diagnose because liquidation would be at/above entry for longs or at/below entry for shorts

**Verify:**
```bash
.venv/Scripts/python -m pytest tests/test_infrastructure/test_full_margin_mode.py tests/test_infrastructure/test_backtest_edge_cases.py -q
```

**Common mistake:** Storing `maintenance_margin_pct` in `ExecutionConfig` but continuing to compute liquidation from leverage only.

---

## Step 4: Add configurable risk price basis
**Files:**
- `finbar/core/domain/entities/execution_config.py`
- `finbar/infrastructure/services/position_executor.py`
- `finbar/infrastructure/services/position_opener.py`
- `packages/strategy-runtime/finbar_strategy_runtime/evaluation/json_risk_price_calculator.py` if adding a reusable calculate-from-anchor API

Default to `signal_close` for backward compatibility. Add `entry_fill` mode to recalculate risk prices from the actual fill price before sizing and validation.

Preferred API on runtime calculator:
```python
def calculate_from_price(risk: RiskSpec | None, bar: dict, side: str, anchor_price: float) -> tuple[float, float]:
    ...
```

If the runtime package does not expose enough risk metadata on `SignalResult`, add metadata in `JsonRuleBasedStrategy` without changing public action semantics.

**Verify:**
```bash
.venv/Scripts/python -m pytest tests/test_infrastructure/test_backtest_edge_cases.py packages/strategy-runtime/tests/contract/test_evaluator_contract.py -q
```

**Common mistake:** Recalculating the size from fill-based stop but leaving the position's stop_price at the signal-close value.

---

## Step 5: Make borrow/funding assumptions explicit and configurable
**Files:**
- `finbar/core/domain/entities/execution_config.py`
- `finbar/infrastructure/services/position_closer.py`
- `finbar/infrastructure/services/margin_account_manager.py`
- `finbar/infrastructure/services/backtest_result_builder.py`

Add diagnostics fields for:
- `borrow_time_basis`
- `funding_schedule`
- `funding_interval_bars`

For timestamp-based borrow, parse full ISO timestamps when available; fallback to calendar-day mode with a diagnostic if parsing fails.

For scheduled funding, apply funding only when the configured bar interval is reached.

**Verify:**
```bash
.venv/Scripts/python -m pytest tests/test_infrastructure/test_full_margin_mode.py tests/test_infrastructure/test_backtest_edge_cases.py -q
```

**Common mistake:** Changing default funding/borrow behaviour without marking it in trust diagnostics or preserving compatibility.

---

## Final verification
After all slices:
```bash
.venv/Scripts/python -m pytest tests -q
cd packages/strategy-runtime && .venv/Scripts/python -m pytest tests -q
```

Expected: all tests pass, and trust diagnostics make the remaining modelling assumptions explicit.
