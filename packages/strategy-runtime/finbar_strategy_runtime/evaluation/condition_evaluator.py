"""ConditionEvaluator — evaluate strategy condition trees against bar data.

Uses two-pass evaluation:
  Pass 1 (collect state): walk the tree and record crossover (left, right)
    pairs into pending_values. Boolean results are ignored.
  Pass 2 (evaluate booleans): walk the tree and compute boolean results.
    This pass can safely use short-circuit any/all because crossover state
    is already recorded from pass 1.
"""

from __future__ import annotations

import math
from typing import Any

from finbar_strategy_runtime.domain.entities.condition import Condition
from finbar_strategy_runtime.domain.entities.condition_group import ConditionGroup
from finbar_strategy_runtime.domain.entities.operand import Operand

PrevValues = dict[str, tuple[float, float]]
PendingValues = dict[str, tuple[float, float]]

_CROSSOVER_OPERATORS = frozenset({"crosses_above", "crosses_below"})


class ConditionEvaluator:
    """Evaluate nested JSON strategy condition groups against enriched bars."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        group: ConditionGroup | None,
        bar: dict,
        previous_values: PrevValues,
        pending_values: PendingValues | None = None,
    ) -> bool:
        """Evaluate a nested condition group against one enriched bar.

        Performs two passes:
        1. Collect crossover state into pending_values (always visits
           every crossover in the tree).
        2. Evaluate boolean result with short-circuit any/all.
        """
        own_pending = pending_values is None
        pv = pending_values if pending_values is not None else {}

        # Pass 1: record crossover state for every crossover in the tree
        self._collect_state(group, bar, pv)

        # Pass 2: evaluate booleans (safe to short-circuit now)
        result = self._evaluate_bool(group, bar, previous_values, pv)

        if own_pending:
            self.commit(previous_values, pv)
        return result

    def commit(
        self,
        previous_values: PrevValues,
        pending_values: PendingValues,
    ) -> None:
        """Commit crossover values collected during one bar evaluation."""
        previous_values.update(pending_values)

    # ------------------------------------------------------------------
    # Pass 1 — collect crossover state (side-effect only, no bool result)
    # ------------------------------------------------------------------

    def _collect_state(
        self,
        group: ConditionGroup | None,
        bar: dict,
        pending_values: PendingValues,
    ) -> None:
        """Walk the tree and record (left, right) for every crossover.

        Non-crossover conditions are skipped entirely in this pass.
        Groups are recursed into to find nested crossovers.
        """
        if group is None:
            return
        if group.kind in ("all", "any"):
            for child in group.children:
                self._collect_state(child, bar, pending_values)
        elif group.kind == "not":
            self._collect_state(group.children[0], bar, pending_values)
        elif group.kind == "condition" and group.condition is not None:
            self._collect_crossover(group.condition, bar, pending_values)

    def _collect_crossover(
        self,
        condition: Condition,
        bar: dict,
        pending_values: PendingValues,
    ) -> None:
        """If this is a crossover condition, resolve operands and record state."""
        if condition.operator not in _CROSSOVER_OPERATORS:
            return
        if condition.right is None:
            return
        left = self._resolve_operand(condition.left, bar)
        right = self._resolve_operand(condition.right, bar)
        left_n = self._to_float(left)
        right_n = self._to_float(right)
        if left_n is None or right_n is None:
            return
        right_label = condition.right.label if condition.right else ""
        key = f"{condition.left.label}:{right_label}:{condition.operator}"
        pending_values[key] = (left_n, right_n)

    # ------------------------------------------------------------------
    # Pass 2 — evaluate booleans (safe to short-circuit)
    # ------------------------------------------------------------------

    def _evaluate_bool(
        self,
        group: ConditionGroup | None,
        bar: dict,
        previous_values: PrevValues,
        pending_values: PendingValues,
    ) -> bool:
        """Evaluate boolean result of a condition tree.

        Uses generator expressions for any/all to short-circuit.
        Crossover state is already in pending_values from pass 1.
        """
        if group is None:
            return False
        if group.kind in ("all", "any"):
            results = (
                self._evaluate_bool(child, bar, previous_values, pending_values)
                for child in group.children
            )
            return all(results) if group.kind == "all" else any(results)
        if group.kind == "not":
            return not self._evaluate_bool(
                group.children[0], bar, previous_values, pending_values
            )
        if group.kind == "condition" and group.condition is not None:
            return self._evaluate_condition(
                group.condition, bar, previous_values, pending_values
            )
        return False

    # ------------------------------------------------------------------
    # Condition evaluation (shared helpers)
    # ------------------------------------------------------------------

    def _evaluate_condition(
        self,
        condition: Condition,
        bar: dict,
        previous_values: PrevValues,
        pending_values: PendingValues,
    ) -> bool:
        left = self._resolve_operand(condition.left, bar)
        operator = condition.operator

        if operator == "exists":
            return left is not None
        if operator == "missing":
            return left is None
        if operator == "is_true":
            return bool(left) is True
        if operator == "is_false":
            return bool(left) is False

        if condition.right is None:
            return False
        right = self._resolve_operand(condition.right, bar)

        if operator in ("between", "not_between"):
            result = self._between(left, right)
            return not result if operator == "not_between" else result

        left_number = self._to_float(left)
        right_number = self._to_float(right)
        if left_number is None or right_number is None:
            return False

        if operator in ("<", ">", "<=", ">=", "==", "!="):
            return self._compare(left_number, operator, right_number)
        if operator in _CROSSOVER_OPERATORS:
            return self._crossed(
                condition, left_number, right_number, previous_values, pending_values
            )
        return False

    @staticmethod
    def _resolve_operand(operand: Operand, bar: dict) -> Any:
        if operand.kind in ("field", "indicator", "feature", "column"):
            value = bar.get(str(operand.value))
            if value is not None:
                if not _is_nan(value):
                    return value
            for source in operand.sources:
                value = bar.get(source)
                if value is not None and not _is_nan(value):
                    return value
            return None
        return operand.value

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(result):
            return None
        return result

    @staticmethod
    def _between(left: Any, right: Any) -> bool:
        left_number = ConditionEvaluator._to_float(left)
        if left_number is None or not isinstance(right, list) or len(right) != 2:
            return False
        low = ConditionEvaluator._to_float(right[0])
        high = ConditionEvaluator._to_float(right[1])
        if low is None or high is None:
            return False
        return low <= left_number <= high

    @staticmethod
    def _compare(left: float, operator: str, right: float) -> bool:
        if operator == "<":
            return left < right
        if operator == ">":
            return left > right
        if operator == "<=":
            return left <= right
        if operator == ">=":
            return left >= right
        if operator == "==":
            return abs(left - right) < 1e-9
        if operator == "!=":
            return abs(left - right) >= 1e-9
        return False

    @staticmethod
    def _crossed(
        condition: Condition,
        left: float,
        right: float,
        previous_values: PrevValues,
        pending_values: PendingValues,
    ) -> bool:
        right_label = condition.right.label if condition.right is not None else ""
        key = f"{condition.left.label}:{right_label}:{condition.operator}"
        previous = previous_values.get(key)
        # NOTE: _collect_state already wrote pending_values[key] in pass 1.
        # We still write here for the case where _crossed is called outside
        # the two-pass flow (e.g., direct calls from tests). This is
        # idempotent — same key, same value.
        pending_values[key] = (left, right)
        if previous is None:
            return False
        previous_left, previous_right = previous
        if condition.operator == "crosses_above":
            return previous_left <= previous_right and left > right
        if condition.operator == "crosses_below":
            return previous_left >= previous_right and left < right
        return False


def _is_nan(value) -> bool:
    """Return True when value is a float NaN."""
    return isinstance(value, float) and value != value
