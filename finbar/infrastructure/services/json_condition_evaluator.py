"""Condition evaluation helpers for v2 JSON strategies."""

from __future__ import annotations

import math
from typing import Any

from finbar.core.domain.entities.condition import Condition
from finbar.core.domain.entities.condition_group import ConditionGroup
from finbar.core.domain.entities.operand import Operand

PrevValues = dict[str, tuple[float, float]]


def evaluate_condition_group(
    group: ConditionGroup | None,
    bar: dict,
    previous_values: PrevValues,
) -> bool:
    """Evaluate a nested condition group against one enriched bar."""
    if group is None:
        return False
    if group.kind in ("all", "any"):
        results = [
            evaluate_condition_group(child, bar, previous_values)
            for child in group.children
        ]
        return all(results) if group.kind == "all" else any(results)
    if group.kind == "not":
        return not evaluate_condition_group(group.children[0], bar, previous_values)
    if group.kind == "condition" and group.condition is not None:
        return _evaluate_condition(group.condition, bar, previous_values)
    return False


def _evaluate_condition(
    condition: Condition,
    bar: dict,
    previous_values: PrevValues,
) -> bool:
    left = _resolve_operand(condition.left, bar)
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
    right = _resolve_operand(condition.right, bar)

    if operator in ("between", "not_between"):
        result = _between(left, right)
        return not result if operator == "not_between" else result

    left_number = _to_float(left)
    right_number = _to_float(right)
    if left_number is None or right_number is None:
        return False

    if operator in ("<", ">", "<=", ">=", "==", "!="):
        return _compare(left_number, operator, right_number)
    if operator in ("crosses_above", "crosses_below"):
        return _crossed(condition, left_number, right_number, previous_values)
    return False


def _resolve_operand(operand: Operand, bar: dict) -> Any:
    if operand.kind in ("field", "indicator", "feature", "column"):
        return bar.get(str(operand.value))
    return operand.value


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


def _between(left: Any, right: Any) -> bool:
    left_number = _to_float(left)
    if left_number is None or not isinstance(right, list) or len(right) != 2:
        return False
    low = _to_float(right[0])
    high = _to_float(right[1])
    if low is None or high is None:
        return False
    return low <= left_number <= high


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


def _crossed(
    condition: Condition,
    left: float,
    right: float,
    previous_values: PrevValues,
) -> bool:
    right_label = condition.right.label if condition.right is not None else ""
    key = f"{condition.left.label}:{right_label}:{condition.operator}"
    previous = previous_values.get(key)
    previous_values[key] = (left, right)
    if previous is None:
        return False
    previous_left, previous_right = previous
    if condition.operator == "crosses_above":
        return previous_left <= previous_right and left > right
    if condition.operator == "crosses_below":
        return previous_left >= previous_right and left < right
    return False
