# Domain Model — Separate Crossover State from Boolean Evaluation

## Problem statement

`ConditionEvaluator._evaluate_group()` currently performs two duties in one recursive walk:

1. **State tracking:** any `crosses_above`/`crosses_below` condition writes `(left, right)` to `pending_values` via `_crossed()`. This side effect happens regardless of whether the crossover returns True or False.

2. **Boolean evaluation:** `any`/`all`/`not` groups compute a boolean result from their children.

These are entangled because `_crossed()` is called during `_evaluate_condition()`, which is called during `_evaluate_group()`. To guarantee state is recorded for every crossover, all children must be evaluated — forcing eager list comprehension instead of short-circuit generator.

### Current code (eager, no short-circuit)

```python
def _evaluate_group(self, group, bar, previous_values, pending_values):
    if group.kind in ("all", "any"):
        results = [
            self._evaluate_group(child, bar, previous_values, pending_values)
            for child in group.children
        ]
        return all(results) if group.kind == "all" else any(results)
```

### Desired behaviour

- All crossover state is recorded for the current bar, regardless of boolean outcome.
- Pure boolean children (comparisons, `is_true`, `between`, etc.) can be short-circuited when the group result is already determined.
- Crossover children deeper in the tree are always visited for state tracking, even if a prior sibling already determined the group's boolean result.

## Design options

### Option A: Two-pass evaluation (recommended)

**First pass — collect state:** Walk the entire tree and evaluate EVERY child that contains or wraps a crossover condition. Collect `(left, right)` pairs into `pending_values`. This pass ignores boolean results.

**Second pass — evaluate booleans:** Walk the tree again and compute boolean results. This pass can safely use short-circuit `any`/`all` because state is already collected. Crossover conditions use the already-computed `pending_values` to check `previous_values` and return their boolean result.

```
Pass 1 (state):                         Pass 2 (bool):
  all [                                   all [
    crossover(sma20, sma50)  ──► pv         crossover(sma20, sma50)  ──► check pv
    vol > 500                               vol > 500                 ──► 100 > 500 = False ──┐
  ]                                       ]                          ◄── short-circuit          │
                                                                                               │
                                          result = False   ◄───────────────────────────────────┘
```

**Pros:**
- Clean separation of concerns.
- Boolean pass gets full short-circuit benefit.
- Easy to reason about and test independently.

**Cons:**
- Two tree walks per evaluation (but the tree is small — max depth 5, typical 2-4 children per group).
- Need to ensure pass-1 doesn't duplicate work that pass-2 will also do.

**Implementation sketch:**
```python
def evaluate(self, group, bar, previous_values, pending_values=None):
    own_pending = pending_values is None
    pv = pending_values if pending_values is not None else {}
    
    # Pass 1: collect all crossover state (ignore boolean results)
    self._collect_state(group, bar, previous_values, pv)
    
    # Pass 2: evaluate booleans (safe to short-circuit)
    result = self._evaluate_bool(group, bar, previous_values, pv)
    
    if own_pending:
        self.commit(previous_values, pv)
    return result
```

`_collect_state` visits every node but only evaluates conditions that are crossovers — boolean conditions are skipped. `_evaluate_bool` is the current eager evaluator but using generator expressions for `any`/`all`.

### Option B: Pre-scan for crossovers

Before evaluating, scan the entire tree to find all crossover conditions. Evaluate just those conditions first to populate `pending_values`, then run the normal evaluation with short-circuit.

**Pros:** Simpler than two-pass — reuses existing `_evaluate_group` for pass 2.

**Cons:** Requires a tree-scanning visitor that finds crossover nodes. The visitor pattern already exists (`ConditionTreeVisitor`) but would need a new implementation.

### Option C: Callback-based state collection

Modify `_evaluate_condition` to accept a callback that is always invoked for crossovers before the boolean check. The callback records state.

**Pros:** Single pass. Minimal refactoring.

**Cons:** Callback overhead on every evaluation. Still entangled — just pushed to a callback.

## Recommendation

**Option A (two-pass)** is recommended. The condition tree is small (max depth 5, typically < 10 nodes total), so two walks are negligible. The clean separation of state collection from boolean evaluation makes the code easier to test, reason about, and optimise independently.

## Affected components

| Component | Change |
|-----------|--------|
| `ConditionEvaluator` | Split `_evaluate_group` into `_collect_state` and `_evaluate_bool` |
| `ConditionEvaluator.evaluate()` | Call collect → evaluate → commit |
| `ConditionEvaluator.commit()` | No change |
| `_evaluate_condition()` | No change (called from both passes; crossovers do state + bool) |
| `_crossed()` | No change |
| `JsonRuleBasedStrategy` | No change (uses `evaluate()` API) |
| `TradingStrategy` interface | No change |

## No changes to

- `Condition`, `ConditionGroup`, `Operand` entities — immutable, unchanged.
- `SignalResult`, `RiskSpec`, `SideRules` — not involved.
- Public API of `ConditionEvaluator` — `evaluate()`, `commit()` signatures unchanged.
- Crossover detection algorithm — `_crossed()` logic unchanged.
- `StrategyDefinitionParser` — not involved.

## Statefulness contract (unchanged)

The two-pass refactor does not change the statefulness contract. `pending_values` is still populated during evaluation and committed to `previous_values` after. The difference is only in execution order: state is collected first, then booleans are evaluated.

| Component | Stateful? | Change? |
|-----------|-----------|---------|
| `TradingStrategy` | Yes | No change |
| `ConditionEvaluator` | Yes | Internal refactor only |
| `IndicatorCalculator` | No | No change |
| `RiskPriceCalculator` | No | No change |
