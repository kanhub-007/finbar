"""Tests for two-pass condition evaluation — separate crossover state from bools.

These tests verify that crossover state is always recorded in pending_values
regardless of whether an any/all group short-circuits its boolean result.
"""

import pytest

from finbar_strategy_runtime.domain.entities.condition import Condition
from finbar_strategy_runtime.domain.entities.condition_group import ConditionGroup
from finbar_strategy_runtime.domain.entities.operand import Operand
from finbar_strategy_runtime.evaluation.condition_evaluator import (
    ConditionEvaluator,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _op(column: str, label: str = "") -> Operand:
    """Build an indicator operand."""
    return Operand(kind="indicator", value=column, label=label, sources=[])


def _const(value) -> Operand:
    """Build a constant operand."""
    return Operand(kind="constant", value=value, sources=[])


def _cond(left_col: str, operator: str, right, *, label: str = "") -> Condition:
    """Build a condition with a left column operand."""
    if isinstance(right, Operand):
        right_op = right
    elif isinstance(right, str) and operator in ("crosses_above", "crosses_below"):
        right_op = _op(right, label=right)
    else:
        right_op = _const(right)
    return Condition(
        left=_op(left_col, label=left_col),
        operator=operator,
        right=right_op,
    )


def _leaf(cond: Condition) -> ConditionGroup:
    """Wrap a condition in a leaf group."""
    return ConditionGroup(kind="condition", condition=cond)


def _group(kind: str, *children: ConditionGroup) -> ConditionGroup:
    """Build a boolean group."""
    return ConditionGroup(kind=kind, children=list(children))


# ---------------------------------------------------------------------------
# Slice 1 Scenario 1: Crossover state recorded when all short-circuits on False
# ---------------------------------------------------------------------------


class TestCrossoverStateSurvivesShortCircuit:
    """Verify crossover state is ALWAYS recorded, even when boolean evaluation
    would short-circuit past the crossover child."""

    def test_all_group_first_child_false_still_records_crossover_state(self):
        """all: [volume > 500, sma_20 crosses_above sma_50]
        Bar: volume=100 → first child False.
        Crossover child must still record (99, 100) in pending_values."""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        entry = _group(
            "all",
            _leaf(_cond("volume", ">", 500)),
            _leaf(_cond("sma_20", "crosses_above", "sma_50")),
        )

        bar = {"sma_20": 99, "sma_50": 100, "volume": 100}
        result = evaluator.evaluate(entry, bar, pv)

        assert result is False
        assert pv.get("sma_20:sma_50:crosses_above") == (99.0, 100.0), (
            f"Crossover state not recorded! pv={pv}"
        )

    def test_any_group_first_child_true_still_records_crossover_state(self):
        """any: [rsi < 30, sma_20 crosses_above sma_50]
        Bar: rsi=25 → first child True.
        Crossover child must still record state."""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        entry = _group(
            "any",
            _leaf(_cond("rsi_14", "<", 30)),
            _leaf(_cond("sma_20", "crosses_above", "sma_50")),
        )

        bar = {"sma_20": 99, "sma_50": 100, "rsi_14": 25}
        result = evaluator.evaluate(entry, bar, pv)

        assert result is True
        assert pv.get("sma_20:sma_50:crosses_above") == (99.0, 100.0), (
            f"Crossover state not recorded when any short-circuits! pv={pv}"
        )

    def test_crossover_first_child_volume_second_both_evaluated(self):
        """all: [sma_20 crosses_above sma_50, volume > 500]
        Bar: volume=100 → second child False, but crossover state still recorded."""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        entry = _group(
            "all",
            _leaf(_cond("sma_20", "crosses_above", "sma_50")),
            _leaf(_cond("volume", ">", 500)),
        )

        bar = {"sma_20": 99, "sma_50": 100, "volume": 100}
        result = evaluator.evaluate(entry, bar, pv)

        assert result is False
        assert pv.get("sma_20:sma_50:crosses_above") == (99.0, 100.0)

    def test_three_children_all_crossovers_recorded(self):
        """all: [cross_a, vol>500, cross_b]
        Bar: volume=100 (middle child False).
        Both cross_a and cross_b must record state."""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        entry = _group(
            "all",
            _leaf(_cond("fast", "crosses_above", "slow")),
            _leaf(_cond("volume", ">", 500)),
            _leaf(_cond("rsi", "crosses_below", "threshold")),
        )

        bar = {
            "fast": 10, "slow": 20,
            "volume": 100,
            "rsi": 70, "threshold": 50,
        }
        result = evaluator.evaluate(entry, bar, pv)

        assert result is False
        assert pv.get("fast:slow:crosses_above") == (10.0, 20.0)
        assert pv.get("rsi:threshold:crosses_below") == (70.0, 50.0)


# ---------------------------------------------------------------------------
# Slice 1 Scenario 3: Two-bar crossover sequence works identically
# ---------------------------------------------------------------------------


class TestTwoBarCrossoverParity:
    """Verify that two-bar crossover sequences work identically to the
    current eager-evaluation implementation."""

    def test_filter_fails_bar1_crossover_triggers_bar2(self):
        """all: [volume > 500, sma_20 crosses_above sma_50]
        Bar 1: volume=100 → False, crossover state recorded.
        Bar 2: volume=2000 → True, crossover detects transition → True."""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        entry = _group(
            "all",
            _leaf(_cond("volume", ">", 500)),
            _leaf(_cond("sma_20", "crosses_above", "sma_50")),
        )

        # Bar 1: filter fails, state recorded
        bar1 = {"sma_20": 99, "sma_50": 100, "volume": 100}
        r1 = evaluator.evaluate(entry, bar1, pv)
        assert r1 is False
        assert "sma_20:sma_50:crosses_above" in pv

        # Bar 2: filter passes, crossover should trigger
        bar2 = {"sma_20": 101, "sma_50": 100, "volume": 2000}
        r2 = evaluator.evaluate(entry, bar2, pv)
        assert r2 is True, (
            f"Crossover not detected on bar 2! pv={pv}"
        )

    def test_crossover_second_bar_with_any_group(self):
        """any: [volume > 500, sma_20 crosses_above sma_50]
        Bar 1: volume=100 (False), crossover state recorded.
        Bar 2: volume=2000 (True) → any=True via short-circuit,
        but crossover was also evaluated and recorded for bar 2."""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        entry = _group(
            "any",
            _leaf(_cond("volume", ">", 500)),
            _leaf(_cond("sma_20", "crosses_above", "sma_50")),
        )

        bar1 = {"sma_20": 99, "sma_50": 100, "volume": 100}
        r1 = evaluator.evaluate(entry, bar1, pv)
        assert r1 is False
        assert pv.get("sma_20:sma_50:crosses_above") == (99.0, 100.0)

        bar2 = {"sma_20": 101, "sma_50": 100, "volume": 2000}
        r2 = evaluator.evaluate(entry, bar2, pv)
        assert r2 is True

    def test_three_bar_sequence_crossover_triggers_on_bar3(self):
        """all: [vol > 500, cross_above(fast, slow)]
        Bar 1: vol=100, fast=10, slow=20 → False, state (10,20)
        Bar 2: vol=2000, fast=10, slow=20 → False (no crossover yet)
        Bar 3: vol=2000, fast=25, slow=20 → True (crossover!)"""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        entry = _group(
            "all",
            _leaf(_cond("volume", ">", 500)),
            _leaf(_cond("fast", "crosses_above", "slow")),
        )

        bar1 = {"fast": 10, "slow": 20, "volume": 100}
        r1 = evaluator.evaluate(entry, bar1, pv)
        assert r1 is False
        assert pv.get("fast:slow:crosses_above") == (10.0, 20.0)

        bar2 = {"fast": 10, "slow": 20, "volume": 2000}
        r2 = evaluator.evaluate(entry, bar2, pv)
        assert r2 is False  # no crossover yet (same values)
        assert pv.get("fast:slow:crosses_above") == (10.0, 20.0)

        bar3 = {"fast": 25, "slow": 20, "volume": 2000}
        r3 = evaluator.evaluate(entry, bar3, pv)
        assert r3 is True, (
            f"Crossover should trigger on bar 3! pv={pv}"
        )


# ---------------------------------------------------------------------------
# Slice 1 Scenario 4: Nested groups propagate state from all levels
# ---------------------------------------------------------------------------


class TestNestedGroupCrossoverState:
    """Verify crossovers at any nesting depth record state."""

    def test_nested_all_inside_any_both_crossovers_recorded(self):
        """any: [all: [cross_a, cross_b], vol > 500]
        Both cross_a and cross_b must record state."""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        inner = _group(
            "all",
            _leaf(_cond("fast", "crosses_above", "slow")),
            _leaf(_cond("rsi", "crosses_below", "threshold")),
        )
        outer = _group("any", inner, _leaf(_cond("volume", ">", 500)))

        bar = {
            "fast": 10, "slow": 20,
            "rsi": 70, "threshold": 50,
            "volume": 100,
        }
        result = evaluator.evaluate(outer, bar, pv)

        # Volume fails, but inner all evaluates both crossovers
        assert result is False
        assert pv.get("fast:slow:crosses_above") == (10.0, 20.0)
        assert pv.get("rsi:threshold:crosses_below") == (70.0, 50.0)

    def test_not_wrapping_crossover_still_records_state(self):
        """not: [crosses_above(fast, slow)]
        State must be recorded even though result is negated."""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        entry = _group(
            "not",
            _leaf(_cond("fast", "crosses_above", "slow")),
        )

        bar = {"fast": 10, "slow": 20}
        result = evaluator.evaluate(entry, bar, pv)

        # No previous value → _crossed returns False → not(False) = True
        assert result is True
        assert pv.get("fast:slow:crosses_above") == (10.0, 20.0)

    def test_not_wrapping_any_with_crossover_still_records_state(self):
        """not: [any: [cross_a, vol>500]]
        Crossover state must be recorded through two levels of wrapping."""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        inner = _group(
            "any",
            _leaf(_cond("fast", "crosses_above", "slow")),
            _leaf(_cond("volume", ">", 500)),
        )
        outer = _group("not", inner)

        bar = {"fast": 10, "slow": 20, "volume": 100}
        result = evaluator.evaluate(outer, bar, pv)

        # any: crossover=False (no previous), vol=False → False
        # not(False) = True
        assert result is True
        assert pv.get("fast:slow:crosses_above") == (10.0, 20.0)


# ---------------------------------------------------------------------------
# Slice 1 Scenario 6: Regression — existing tests pass
# ---------------------------------------------------------------------------


class TestRegressionParity:
    """Smoke tests for parity with current eager-evaluation behavior."""

    def test_simple_all_group_without_crossovers(self):
        """all: [close > 100, volume > 500] — no crossovers, pure booleans."""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        entry = _group(
            "all",
            _leaf(_cond("close", ">", 100)),
            _leaf(_cond("volume", ">", 500)),
        )

        assert evaluator.evaluate(entry, {"close": 150, "volume": 600}, pv) is True
        assert evaluator.evaluate(entry, {"close": 90, "volume": 600}, pv) is False

    def test_simple_any_group_without_crossovers(self):
        """any: [close > 100, volume > 500] — no crossovers."""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        entry = _group(
            "any",
            _leaf(_cond("close", ">", 100)),
            _leaf(_cond("volume", ">", 500)),
        )

        assert evaluator.evaluate(entry, {"close": 90, "volume": 600}, pv) is True
        assert evaluator.evaluate(entry, {"close": 90, "volume": 100}, pv) is False

    def test_all_operators_still_work(self):
        """All comparison operators still produce correct results."""
        evaluator = ConditionEvaluator()
        pv: dict = {}

        for op, left, right, expected in [
            ("<", 10, 20, True),
            (">", 20, 10, True),
            ("<=", 10, 10, True),
            (">=", 10, 10, True),
            ("==", 10, 10, True),
            ("!=", 10, 20, True),
            ("between", 50, [30, 70], True),
        ]:
            entry = _leaf(Condition(
                left=_const(left), operator=op, right=_const(right)
            ))
            assert evaluator.evaluate(entry, {}, pv) is expected, (
                f"Operator {op} failed: {left} {op} {right}"
            )
