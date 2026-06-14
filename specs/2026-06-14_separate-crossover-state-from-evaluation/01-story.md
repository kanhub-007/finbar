# Separate Crossover State Tracking from Boolean Evaluation

## User Story
As a strategy runtime maintainer, I want crossover state tracking to be separated from boolean condition evaluation, so that `any`/`all` condition groups can safely short-circuit without losing crossover state updates, improving both correctness guarantees and evaluation performance.

## Context

The `ConditionEvaluator._evaluate_group()` method currently performs two duties in a single recursive walk: (1) it tracks crossover state by writing to a mutable `pending_values` dict, and (2) it computes boolean results for `any`/`all`/`not` group nodes. These concerns are entangled: `_crossed()` always writes `pending_values[key] = (left, right)` as a side effect, regardless of whether the crossover condition returns `True` or `False`.

This entanglement forces eager evaluation of ALL children in `any`/`all` groups via a list comprehension (`[self._evaluate_group(child, ...) for child in group.children]`). If the list comprehension were changed to a generator for short-circuit evaluation, children skipped by `any` (first True) or `all` (first False) would never execute — and their crossover state would never be recorded.

**Concrete failure mode:** A strategy with `all: [volume > 500, sma_20 crosses_above sma_50]` where volume=100 on bar 1. With eager evaluation, the crossover child is still evaluated, recording `(99, 100)` in `pending_values`. On bar 2 when volume=2000, the crossover detects the transition and triggers. With short-circuit, bar 1 skips the crossover child, `pending_values` stays empty, and bar 2 never triggers — the signal is missed.

The desired state is: crossover state is ALWAYS recorded for the current bar (regardless of boolean outcome), AND boolean evaluation can use efficient short-circuit logic. These are two separate concerns that should be two separate passes or mechanisms.

## Non-Goals
- Changing the public API of `ConditionEvaluator` or `TradingStrategy`.
- Changing the crossover detection algorithm itself (the `crosses_above`/`crosses_below` logic is correct).
- Adding new operators or condition types.
- Optimising any other part of the evaluator (e.g., `_resolve_operand`, `_to_float`).
- Making the evaluator vectorised/pandas-based (that is a separate performance concern).
