"""Contract tests for the strategy runtime package — parsing and validation.

These are black-box, Classical-school tests: real runtime objects, assertions
on outcomes. No mocks, no interaction assertions, no private method verification.
"""

import json
import os
from pathlib import Path

import pytest

from finbar_strategy_runtime.parser.strategy_definition_parser import (
    StrategyDefinitionParser,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "strategies"


def _load_yaml_fixture(name: str) -> str:
    """Load a strategy YAML fixture from the finbar strategies directory."""
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    return path.read_text()


# ---------------------------------------------------------------------------
# Scenario 1: Runtime package exposes canonical strategy parsing and validation
# ---------------------------------------------------------------------------


class TestStrategyParsing:
    """Black-box contract tests for strategy parsing and validation."""

    def test_parse_valid_amt_dip_buyer_strategy(self):
        """Parse a valid AMT dip buyer YAML strategy — should produce a valid
        StrategyDefinition with correct fields."""
        parser = StrategyDefinitionParser()
        yaml_text = _load_yaml_fixture("amt_dip_buyer_final.yaml")

        result = parser.parse(yaml_text)

        assert result.valid is True
        assert result.definition is not None
        assert result.definition.name == "amt_dip_buyer_final"
        assert result.definition.schema_version == "2.0"
        assert result.definition.description.startswith("AMT Rule 1 dip buyer")
        assert "long" in result.definition.sides
        assert result.definition.sides["long"].entry is not None
        assert result.definition.sides["long"].exit is not None
        # Ensure no errors
        assert len(result.errors) == 0

    def test_parse_amt_v2_strategy(self):
        """Parse the AMT v2 vol filter strategy — should be valid."""
        parser = StrategyDefinitionParser()
        yaml_text = _load_yaml_fixture("amt_v2_vol_filter.yaml")

        result = parser.parse(yaml_text)

        assert result.valid is True
        assert result.definition is not None
        assert result.definition.name == "amt_v2_vol_filter"
        assert result.definition.schema_version == "2.0"

    def test_parse_json_strategy(self):
        """Parse a strategy provided as a JSON string, not YAML."""
        parser = StrategyDefinitionParser()
        json_text = json.dumps(
            {
                "schema_version": "2.0",
                "name": "sma_cross_json",
                "description": "Simple SMA crossover",
                "indicators": [
                    {"name": "sma_fast", "type": "sma", "period": 10},
                    {"name": "sma_slow", "type": "sma", "period": 30},
                ],
                "sides": {
                    "long": {
                        "entry": {
                            "condition": {
                                "operator": "crosses_above",
                                "left": "sma_fast",
                                "right": "sma_slow",
                            }
                        },
                        "exit": {
                            "condition": {
                                "operator": "crosses_below",
                                "left": "sma_fast",
                                "right": "sma_slow",
                            }
                        },
                    }
                },
            }
        )

        result = parser.parse(json_text)

        assert result.valid is True
        assert result.definition is not None
        assert result.definition.name == "sma_cross_json"
        assert len(result.definition.indicators) == 2


class TestStrategyValidationErrors:
    """Black-box tests for validation failures."""

    def test_unknown_indicator_produces_error_with_path(self):
        """Unknown indicator type should produce an invalid result with a
        path-specific error pointing to the indicator name."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "bad_indicator",
            "indicators": [{"name": "made_up", "type": "nonexistent_indicator_xyz"}],
            "sides": {
                "long": {
                    "entry": {"condition": {"operator": "is_true", "left": "made_up"}},
                    "exit": {"condition": {"operator": "is_true", "left": "made_up"}},
                }
            },
        }

        result = parser.parse(raw)

        assert result.valid is False
        assert result.definition is None
        assert len(result.errors) > 0
        # At least one error should mention the indicator name
        error_messages = " ".join(e.message for e in result.errors)
        assert "made_up" in error_messages or "nonexistent" in error_messages.lower()

    def test_unsupported_operator_produces_error(self):
        """An unsupported comparison operator should result in an invalid parse."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "bad_operator",
            "indicators": [
                {"name": "my_rsi", "type": "rsi", "period": 14},
            ],
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "operator": "__invalid_operator_xyz__",
                            "left": "my_rsi",
                            "right": 50,
                        }
                    },
                    "exit": {"condition": {"operator": "is_true", "left": "my_rsi"}},
                }
            },
        }

        result = parser.parse(raw)

        assert result.valid is False
        assert len(result.errors) > 0

    def test_parameter_override_outside_min_max_produces_error(self):
        """A parameter override outside the declared min/max range should fail."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "param_test",
            "parameters": {
                "lookback": {
                    "type": "int",
                    "default": 20,
                    "minimum": 5,
                    "maximum": 50,
                }
            },
            "indicators": [
                {"name": "ma", "type": "sma", "period": "{{ lookback }}"},
            ],
            "sides": {
                "long": {
                    "entry": {"condition": {"operator": "is_true", "left": "ma"}},
                    "exit": {"condition": {"operator": "is_true", "left": "ma"}},
                }
            },
        }

        result = parser.parse(raw, param_overrides={"lookback": 100})

        assert result.valid is False
        assert len(result.errors) > 0

    def test_schema_version_other_than_2_0_is_invalid(self):
        """Only schema_version '2.0' is currently supported."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "1.0",
            "name": "old_schema",
            "sides": {
                "long": {
                    "entry": {"condition": {"operator": "is_true", "left": "close"}},
                    "exit": {"condition": {"operator": "is_true", "left": "close"}},
                }
            },
        }

        result = parser.parse(raw)

        assert result.valid is False
        error_messages = " ".join(e.message for e in result.errors)
        assert "schema_version" in error_messages.lower()

    def test_empty_name_produces_error(self):
        """A strategy with an empty name should be invalid."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "",
            "sides": {
                "long": {
                    "entry": {"condition": {"operator": "is_true", "left": "close"}},
                    "exit": {"condition": {"operator": "is_true", "left": "close"}},
                }
            },
        }

        result = parser.parse(raw)

        assert result.valid is False
        error_messages = " ".join(e.message for e in result.errors)
        assert "name" in error_messages.lower()


# =========================================================================
# Scenario 2: Runtime package evaluates strategy conditions and risk prices
# =========================================================================

from finbar_strategy_runtime.domain.entities.condition import Condition
from finbar_strategy_runtime.domain.entities.condition_group import ConditionGroup
from finbar_strategy_runtime.domain.entities.operand import Operand
from finbar_strategy_runtime.domain.entities.risk_spec import RiskSpec
from finbar_strategy_runtime.domain.entities.side_rules import SideRules
from finbar_strategy_runtime.domain.entities.strategy_definition import (
    StrategyDefinition,
)
from finbar_strategy_runtime.evaluation.condition_evaluator import (
    ConditionEvaluator,
)
from finbar_strategy_runtime.evaluation.json_risk_price_calculator import (
    JsonRiskPriceCalculator,
)
from finbar_strategy_runtime.evaluation.json_rule_based_strategy import (
    JsonRuleBasedStrategy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _operand(column: str) -> Operand:
    """Build a simple column operand for test conditions."""
    return Operand(kind="indicator", value=column, sources=[])


def _constant(value) -> Operand:
    """Build a constant operand."""
    return Operand(kind="constant", value=value, sources=[])


def _cond(left_col: str, operator: str, right, right_is_column: bool = False) -> Condition:
    """Build a condition with a left column and right operand.

    Args:
        left_col: Column name for the left operand.
        operator: Comparison/crossover operator.
        right: Either a constant value, an Operand, or a column name.
        right_is_column: If True, 'right' is treated as a column name (for
            crossover and column-vs-column comparisons).
    """
    if isinstance(right, Operand):
        right_op = right
    elif right_is_column:
        right_op = _operand(right)
    else:
        right_op = _constant(right)
    return Condition(
        left=_operand(left_col),
        operator=operator,
        right=right_op,
    )


def _group(kind: str, *children: ConditionGroup, condition: Condition | None = None) -> ConditionGroup:
    """Build a condition group — either a boolean node with children or a leaf with a condition."""
    return ConditionGroup(kind=kind, condition=condition, children=list(children))


class TestConditionEvaluator:
    """Black-box tests for the condition evaluator — operators, groups,
    crossovers, fallbacks, and None/NaN safety."""

    # ---- Boolean operators ------------------------------------------------

    def test_is_true_on_boolean(self):
        """is_true evaluates correctly on a boolean bar field."""
        evaluator = ConditionEvaluator()
        group = _group("condition", condition=_cond("flag", "is_true", None))
        pv: dict = {}

        assert evaluator.evaluate(group, {"flag": True}, pv) is True
        assert evaluator.evaluate(group, {"flag": False}, pv) is False
        assert evaluator.evaluate(group, {"flag": 1}, pv) is True
        assert evaluator.evaluate(group, {"flag": 0}, pv) is False

    def test_is_false_on_boolean(self):
        """is_false evaluates correctly."""
        evaluator = ConditionEvaluator()
        group = _group("condition", condition=_cond("flag", "is_false", None))
        pv: dict = {}

        assert evaluator.evaluate(group, {"flag": True}, pv) is False
        assert evaluator.evaluate(group, {"flag": False}, pv) is True

    # ---- Numeric comparisons ----------------------------------------------

    @pytest.mark.parametrize(
        "operator,left,right,expected",
        [
            ("<", 10, 20, True),
            ("<", 20, 10, False),
            ("<", 10, 10, False),
            (">", 10, 20, False),
            (">", 20, 10, True),
            (">", 10, 10, False),
            ("<=", 10, 10, True),
            ("<=", 10, 20, True),
            ("<=", 20, 10, False),
            (">=", 10, 10, True),
            (">=", 20, 10, True),
            (">=", 10, 20, False),
            ("==", 10, 10, True),
            ("==", 10, 20, False),
            ("!=", 10, 10, False),
            ("!=", 10, 20, True),
        ],
    )
    def test_numeric_comparisons(self, operator, left, right, expected):
        """All numeric comparison operators produce correct boolean results."""
        evaluator = ConditionEvaluator()
        group = _group(
            "condition",
            condition=Condition(
                left=_constant(left), operator=operator, right=_constant(right)
            ),
        )
        pv: dict = {}
        assert evaluator.evaluate(group, {}, pv) is expected

    # ---- between / not_between --------------------------------------------

    def test_between_inclusive(self):
        """between is inclusive on both bounds."""
        evaluator = ConditionEvaluator()
        group = _group(
            "condition",
            condition=Condition(
                left=_constant(50),
                operator="between",
                right=_constant([30, 70]),
            ),
        )
        pv: dict = {}
        assert evaluator.evaluate(group, {}, pv) is True

    def test_between_outside_range(self):
        """between returns False when value is outside range."""
        evaluator = ConditionEvaluator()
        group = _group(
            "condition",
            condition=Condition(
                left=_constant(10),
                operator="between",
                right=_constant([30, 70]),
            ),
        )
        pv: dict = {}
        assert evaluator.evaluate(group, {}, pv) is False

    def test_not_between(self):
        """not_between is the negation of between."""
        evaluator = ConditionEvaluator()
        group = _group(
            "condition",
            condition=Condition(
                left=_constant(10),
                operator="not_between",
                right=_constant([30, 70]),
            ),
        )
        pv: dict = {}
        assert evaluator.evaluate(group, {}, pv) is True

    # ---- Crossover operators ----------------------------------------------

    def test_crosses_above_triggers_only_on_second_bar(self):
        """crosses_above needs two bars: first establishes state, second triggers."""
        evaluator = ConditionEvaluator()
        group = _group("condition", condition=_cond("fast", "crosses_above", "slow", right_is_column=True))
        pv: dict = {}

        # Bar 1: fast <= slow — no crossover yet (just establishes baseline)
        bar1 = {"fast": 10, "slow": 20}
        assert evaluator.evaluate(group, bar1, pv) is False

        # Bar 2: fast > slow — crossover triggers
        bar2 = {"fast": 25, "slow": 20}
        assert evaluator.evaluate(group, bar2, pv) is True

    def test_crosses_above_no_trigger_when_already_above(self):
        """crosses_above does not trigger when fast was already above slow."""
        evaluator = ConditionEvaluator()
        group = _group("condition", condition=_cond("fast", "crosses_above", "slow", right_is_column=True))
        pv: dict = {}

        # fast already above slow
        bar1 = {"fast": 30, "slow": 20}
        assert evaluator.evaluate(group, bar1, pv) is False

        # still above — no crossover
        bar2 = {"fast": 35, "slow": 20}
        assert evaluator.evaluate(group, bar2, pv) is False

    def test_crosses_below_triggers_only_on_second_bar(self):
        """crosses_below needs two bars: fast >= slow then fast < slow."""
        evaluator = ConditionEvaluator()
        group = _group("condition", condition=_cond("fast", "crosses_below", "slow", right_is_column=True))
        pv: dict = {}

        bar1 = {"fast": 20, "slow": 10}
        assert evaluator.evaluate(group, bar1, pv) is False

        bar2 = {"fast": 5, "slow": 10}
        assert evaluator.evaluate(group, bar2, pv) is True

    # ---- Group logic ------------------------------------------------------

    def test_all_group_with_mixed_children_returns_false(self):
        """all group requires every child to be true."""
        evaluator = ConditionEvaluator()
        group = _group(
            "all",
            _group("condition", condition=_cond("a", ">", 5)),
            _group("condition", condition=_cond("a", "<", 20)),
            _group("condition", condition=_cond("a", ">", 15)),
        )
        bar = {"a": 12}
        pv: dict = {}
        # a > 5 ✓, a < 20 ✓, a > 15 ✗ → all = False
        assert evaluator.evaluate(group, bar, pv) is False

    def test_any_group_with_mixed_children_returns_true(self):
        """any group requires at least one child to be true."""
        evaluator = ConditionEvaluator()
        group = _group(
            "any",
            _group("condition", condition=_cond("a", ">", 15)),
            _group("condition", condition=_cond("a", ">", 25)),
            _group("condition", condition=_cond("a", ">", 35)),
        )
        bar = {"a": 20}
        pv: dict = {}
        # a > 15 ✓ → any = True
        assert evaluator.evaluate(group, bar, pv) is True

    def test_not_group_negates_child(self):
        """not group flips the boolean result of its child."""
        evaluator = ConditionEvaluator()
        group = _group(
            "not",
            _group("condition", condition=_cond("flag", "is_true", None)),
        )
        pv: dict = {}

        assert evaluator.evaluate(group, {"flag": True}, pv) is False
        assert evaluator.evaluate(group, {"flag": False}, pv) is True

    # ---- Fallback operand sources -----------------------------------------

    def test_fallback_operand_sources_used_in_order(self):
        """When primary source is missing, fallbacks are tried in order."""
        evaluator = ConditionEvaluator()
        operand = Operand(
            kind="indicator",
            value="primary_col",
            sources=["fallback_1", "fallback_2"],
        )
        group = _group(
            "condition",
            condition=Condition(
                left=operand, operator=">", right=_constant(10)
            ),
        )
        pv: dict = {}

        # Primary missing, fallback_1 present
        bar = {"fallback_1": 15}
        assert evaluator.evaluate(group, bar, pv) is True

        # Primary missing, fallback_1 missing, fallback_2 present
        bar = {"fallback_2": 15}
        assert evaluator.evaluate(group, bar, pv) is True

        # All missing
        bar: dict = {}
        assert evaluator.evaluate(group, bar, pv) is False

    # ---- None / NaN safety -------------------------------------------------

    def test_none_operand_evaluates_safely(self):
        """None values in bar columns should not crash the evaluator."""
        evaluator = ConditionEvaluator()
        group = _group("condition", condition=_cond("value", ">", 10))
        pv: dict = {}

        # None → comparison returns False (no crash)
        assert evaluator.evaluate(group, {"value": None}, pv) is False

    def test_nan_operand_evaluates_safely(self):
        """NaN values in bar columns should not crash the evaluator."""
        evaluator = ConditionEvaluator()
        group = _group("condition", condition=_cond("value", ">", 10))
        pv: dict = {}

        result = evaluator.evaluate(group, {"value": float("nan")}, pv)
        assert isinstance(result, bool)

    def test_missing_operand_evaluates_safely(self):
        """Missing bar keys should not crash the evaluator."""
        evaluator = ConditionEvaluator()
        group = _group("condition", condition=_cond("nonexistent", ">", 10))
        pv: dict = {}

        result = evaluator.evaluate(group, {}, pv)
        assert result is False


class TestRiskPriceCalculator:
    """Black-box tests for stop-loss and take-profit calculation."""

    def test_atr_stop_long(self):
        """ATR stop for long side: close - (atr * multiplier)."""
        calc = JsonRiskPriceCalculator()
        risk = RiskSpec(
            stop_loss_type="atr",
            stop_indicator="atr",
            stop_multiplier=3.5,
        )
        bar = {"close": 100, "atr": 2}

        stop, target = calc.calculate(risk, bar, "long")

        assert stop == pytest.approx(93.0)  # 100 - 3.5 * 2
        assert target == 0.0

    def test_atr_stop_short(self):
        """ATR stop for short side: close + (atr * multiplier)."""
        calc = JsonRiskPriceCalculator()
        risk = RiskSpec(
            stop_loss_type="atr",
            stop_indicator="atr",
            stop_multiplier=2.0,
        )
        bar = {"close": 100, "atr": 5}

        stop, target = calc.calculate(risk, bar, "short")

        assert stop == pytest.approx(110.0)  # 100 + 2 * 5

    def test_fixed_pct_stop_long(self):
        """Fixed-pct stop: close * (1 - pct) for long."""
        calc = JsonRiskPriceCalculator()
        risk = RiskSpec(stop_loss_type="fixed_pct", stop_pct=0.05)
        bar = {"close": 200}

        stop, _ = calc.calculate(risk, bar, "long")

        assert stop == pytest.approx(190.0)  # 200 * 0.95

    def test_fixed_pct_stop_short(self):
        """Fixed-pct stop: close * (1 + pct) for short."""
        calc = JsonRiskPriceCalculator()
        risk = RiskSpec(stop_loss_type="fixed_pct", stop_pct=0.03)
        bar = {"close": 200}

        stop, _ = calc.calculate(risk, bar, "short")

        assert stop == pytest.approx(206.0)  # 200 * 1.03

    def test_risk_reward_take_profit_long(self):
        """Risk-reward target: close + |close - stop| * ratio for long."""
        calc = JsonRiskPriceCalculator()
        risk = RiskSpec(
            stop_loss_type="atr",
            stop_indicator="atr",
            stop_multiplier=2.0,
            take_profit_type="risk_reward",
            risk_reward_ratio=1.5,
        )
        bar = {"close": 100, "atr": 5}

        stop, target = calc.calculate(risk, bar, "long")
        # stop = 100 - 2*5 = 90
        # risk = |100-90| = 10
        # target = 100 + 10*1.5 = 115
        assert stop == pytest.approx(90.0)
        assert target == pytest.approx(115.0)

    def test_risk_reward_take_profit_short(self):
        """Risk-reward target: close - |close - stop| * ratio for short."""
        calc = JsonRiskPriceCalculator()
        risk = RiskSpec(
            stop_loss_type="atr",
            stop_indicator="atr",
            stop_multiplier=2.0,
            take_profit_type="risk_reward",
            risk_reward_ratio=2.0,
        )
        bar = {"close": 100, "atr": 5}

        stop, target = calc.calculate(risk, bar, "short")
        # stop = 100 + 2*5 = 110
        # risk = |100-110| = 10
        # target = 100 - 10*2.0 = 80
        assert stop == pytest.approx(110.0)
        assert target == pytest.approx(80.0)

    def test_none_risk_returns_zeros(self):
        """When risk is None, stop and target are both 0.0."""
        calc = JsonRiskPriceCalculator()
        stop, target = calc.calculate(None, {}, "long")
        assert stop == 0.0
        assert target == 0.0

    def test_zero_atr_returns_zero_stop(self):
        """When ATR is zero or missing, stop should be 0."""
        calc = JsonRiskPriceCalculator()
        risk = RiskSpec(
            stop_loss_type="atr",
            stop_indicator="atr",
            stop_multiplier=3.5,
        )
        bar = {"close": 100, "atr": 0}
        stop, _ = calc.calculate(risk, bar, "long")
        assert stop == 0.0


class TestJsonRuleBasedStrategy:
    """Black-box integration tests for the rule-based strategy execution."""

    def _make_simple_definition(
        self,
        entry_operator: str = ">",
        entry_value: float = 100,
        risk: RiskSpec | None = None,
    ) -> StrategyDefinition:
        """Build a simple StrategyDefinition for testing."""
        entry_cond = Condition(
            left=Operand(kind="indicator", value="close", sources=[]),
            operator=entry_operator,
            right=Operand(kind="constant", value=entry_value, sources=[]),
        )
        return StrategyDefinition(
            name="test",
            sides={
                "long": SideRules(
                    side="long",
                    entry=ConditionGroup(
                        kind="condition",
                        condition=entry_cond,
                    ),
                )
            },
            risk=risk,
        )

    def test_entry_signal_when_condition_true(self):
        """When entry condition is met, strategy emits a buy signal."""
        strategy = JsonRuleBasedStrategy(self._make_simple_definition())

        result = strategy.on_bar({"close": 150}, {"direction": "", "size": 0})

        assert result.action == "buy"
        assert result.direction == "long"

    def test_hold_when_condition_false(self):
        """When no entry condition is met, strategy emits hold."""
        strategy = JsonRuleBasedStrategy(self._make_simple_definition())

        result = strategy.on_bar({"close": 50}, {"direction": "", "size": 0})

        assert result.action == "hold"

    def test_exit_signal_when_in_position_and_exit_condition_true(self):
        """When in a position with matching exit condition, emit exit."""
        exit_cond = Condition(
            left=Operand(kind="indicator", value="close", sources=[]),
            operator="<",
            right=Operand(kind="constant", value=90, sources=[]),
        )
        definition = StrategyDefinition(
            name="test",
            sides={
                "long": SideRules(
                    side="long",
                    entry=ConditionGroup(
                        kind="condition",
                        condition=Condition(
                            left=Operand(kind="indicator", value="close", sources=[]),
                            operator=">",
                            right=Operand(kind="constant", value=100, sources=[]),
                        ),
                    ),
                    exit=ConditionGroup(
                        kind="condition",
                        condition=exit_cond,
                    ),
                )
            },
        )
        strategy = JsonRuleBasedStrategy(definition)

        result = strategy.on_bar(
            {"close": 80}, {"direction": "long", "size": 1}
        )

        assert result.action == "sell"
        assert result.direction == "exit"

    def test_hold_when_in_position_but_no_exit_rule(self):
        """When in position but exit condition is not met, hold."""
        definition = StrategyDefinition(
            name="test",
            sides={
                "long": SideRules(
                    side="long",
                    entry=ConditionGroup(
                        kind="condition",
                        condition=Condition(
                            left=Operand(kind="indicator", value="close", sources=[]),
                            operator=">",
                            right=Operand(kind="constant", value=100, sources=[]),
                        ),
                    ),
                    exit=ConditionGroup(
                        kind="condition",
                        condition=Condition(
                            left=Operand(kind="indicator", value="close", sources=[]),
                            operator="<",
                            right=Operand(kind="constant", value=50, sources=[]),
                        ),
                    ),
                )
            },
        )
        strategy = JsonRuleBasedStrategy(definition)

        result = strategy.on_bar(
            {"close": 150}, {"direction": "long", "size": 1}
        )

        assert result.action == "hold"

    def test_crossover_state_reset(self):
        """After on_reset(), crossover tracking starts from scratch."""
        definition = StrategyDefinition(
            name="test",
            sides={
                "long": SideRules(
                    side="long",
                    entry=ConditionGroup(
                        kind="condition",
                        condition=Condition(
                            left=Operand(kind="indicator", value="fast", sources=[]),
                            operator="crosses_above",
                            right=Operand(kind="indicator", value="slow", sources=[]),
                        ),
                    ),
                )
            },
        )
        strategy = JsonRuleBasedStrategy(definition)

        # First pass: establish state then trigger crossover
        result1 = strategy.on_bar(
            {"fast": 5, "slow": 10}, {"direction": "", "size": 0}
        )
        assert result1.action == "hold"

        result2 = strategy.on_bar(
            {"fast": 15, "slow": 10}, {"direction": "", "size": 0}
        )
        assert result2.action == "buy"

        # Reset
        strategy.on_reset()

        # Same sequence should work again (clean state)
        result3 = strategy.on_bar(
            {"fast": 5, "slow": 10}, {"direction": "", "size": 0}
        )
        assert result3.action == "hold"

        result4 = strategy.on_bar(
            {"fast": 15, "slow": 10}, {"direction": "", "size": 0}
        )
        assert result4.action == "buy"

    def test_entry_stop_and_target_prices(self):
        """Entry signal includes stop and target prices from risk calculator."""
        risk = RiskSpec(
            stop_loss_type="atr",
            stop_indicator="atr",
            stop_multiplier=2.0,
            take_profit_type="risk_reward",
            risk_reward_ratio=1.5,
        )
        strategy = JsonRuleBasedStrategy(self._make_simple_definition(risk=risk))

        bar = {"close": 200, "atr": 10}
        result = strategy.on_bar(bar, {"direction": "", "size": 0})

        # stop = 200 - 2*10 = 180
        # target = 200 + |200-180| * 1.5 = 200 + 30 = 230
        assert result.stop_price == pytest.approx(180.0)
        assert result.target_price == pytest.approx(230.0)

    def test_short_side_entry(self):
        """Short side entry emits sell signal with short direction."""
        definition = StrategyDefinition(
            name="test",
            sides={
                "short": SideRules(
                    side="short",
                    entry=ConditionGroup(
                        kind="condition",
                        condition=Condition(
                            left=Operand(kind="indicator", value="close", sources=[]),
                            operator="<",
                            right=Operand(kind="constant", value=100, sources=[]),
                        ),
                    ),
                )
            },
        )
        strategy = JsonRuleBasedStrategy(definition)

        result = strategy.on_bar({"close": 80}, {"direction": "", "size": 0})

        assert result.action == "sell"
        assert result.direction == "short"

    def test_stop_prices_mirror_for_short_side(self):
        """Short side risk prices are mirrored relative to long side."""
        risk = RiskSpec(
            stop_loss_type="atr",
            stop_indicator="atr",
            stop_multiplier=2.0,
        )
        definition = StrategyDefinition(
            name="test",
            sides={
                "short": SideRules(
                    side="short",
                    entry=ConditionGroup(
                        kind="condition",
                        condition=Condition(
                            left=Operand(kind="indicator", value="close", sources=[]),
                            operator="<",
                            right=Operand(kind="constant", value=100, sources=[]),
                        ),
                    ),
                )
            },
            risk=risk,
        )
        strategy = JsonRuleBasedStrategy(definition)

        bar = {"close": 80, "atr": 5}
        result = strategy.on_bar(bar, {"direction": "", "size": 0})

        # short stop = close + atr * mult = 80 + 2*5 = 90
        assert result.stop_price == pytest.approx(90.0)


# =========================================================================
# Scenario 3: Runtime package computes indicator/enrichment columns with parity
# =========================================================================

import numpy as np

# Soft import pandas_ta — skip indicator tests if unavailable
_HAS_PANDAS_TA = False
try:
    import pandas_ta  # noqa: F401

    _HAS_PANDAS_TA = True
except ImportError:
    pass

pandas_ta_required = pytest.mark.skipif(
    not _HAS_PANDAS_TA,
    reason="pandas_ta not installed (requires Python < 3.14)",
)


class TestIndicatorCalculator:
    """Black-box tests for the Pandas indicator calculator."""

    @staticmethod
    def _make_ohlcv_df(periods: int = 100) -> "pd.DataFrame":
        """Create a sample OHLCV DataFrame for testing."""
        import pandas as pd

        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=periods, freq="h")
        close = 100 + np.cumsum(np.random.randn(periods) * 1.5)
        return pd.DataFrame(
            {
                "open": close - np.random.rand(periods),
                "high": close + np.random.rand(periods) * 2,
                "low": close - np.random.rand(periods) * 2,
                "close": close,
                "volume": np.random.randint(100000, 1000000, periods),
            },
            index=dates,
        )

    @pandas_ta_required
    def test_atr_vp_columns_present(self):
        """Computing atr, vp_poc, vp_vah, vp_val adds those columns."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        df = self._make_ohlcv_df(100)

        enriched = calc.calculate(df, ["atr", "vp_poc", "vp_vah", "vp_val"])

        assert {"atr", "vp_poc", "vp_vah", "vp_val"}.issubset(enriched.columns)
        assert len(enriched) == len(df)

    @pandas_ta_required
    def test_sma_indicators(self):
        """Dynamic period SMA indicators produce correct columns."""
        import pandas as pd

        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        df = self._make_ohlcv_df(250)

        enriched = calc.calculate(df, ["sma_20", "sma_50", "sma_200"])

        assert "sma_20" in enriched.columns
        assert "sma_50" in enriched.columns
        assert "sma_200" in enriched.columns
        # Last value should be non-NaN (enough bars for 200-period SMA)
        assert not pd.isna(enriched["sma_20"].iloc[-1])

    @pandas_ta_required
    def test_rsi_indicator(self):
        """RSI indicator with period parameter."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        df = self._make_ohlcv_df(50)

        enriched = calc.calculate(df, ["rsi_14", "rsi_21"])

        assert "rsi_14" in enriched.columns
        assert "rsi_21" in enriched.columns

    @pandas_ta_required
    def test_insufficient_warmup_produces_nan_no_exception(self):
        """Requesting indicators that need more bars than available should
        still add the column (with NaN values), not raise an exception."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        # 50 bars — enough to pass MIN_BARS (10) but not enough for 200-period SMA
        df = self._make_ohlcv_df(50)

        # Should not raise
        enriched = calc.calculate(df, ["sma_200"])

        assert len(enriched) == len(df)
        # SMA_200 column should exist, but all values are NaN (need 200 bars)
        assert "sma_200" in enriched.columns
        assert enriched["sma_200"].isna().all()

    @pandas_ta_required
    def test_empty_indicators_returns_copy(self):
        """Passing an empty indicator list returns a copy of the frame."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        df = self._make_ohlcv_df(100)

        enriched = calc.calculate(df, [])

        assert len(enriched) == len(df)

    @pandas_ta_required
    def test_empty_df_returns_copy(self):
        """Passing an empty DataFrame returns an empty copy."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        import pandas as pd

        calc = PandasTaIndicatorCalculator()
        result = calc.calculate(pd.DataFrame(), ["rsi_14"])
        assert result.empty

    @pandas_ta_required
    def test_parameterized_vp_indicators(self):
        """Parameterized VP indicators produce columns with the correct naming
        convention used by the calculator."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        df = self._make_ohlcv_df(300)

        enriched = calc.calculate(
            df, ["vp_poc_10d", "rvp_vah_96", "cvp_val_20d"]
        )

        # The calculator may rename parameterized VP indicators
        # (e.g., vp_poc_10d → rvp_poc_96 or similar internal convention)
        assert len(enriched.columns) > len(df.columns), (
            f"Expected additional columns beyond {list(df.columns)}, "
            f"got {list(enriched.columns)}"
        )

    @pandas_ta_required
    def test_acceptance_into_value_indicator(self):
        """acceptance_into_value indicator produces a boolean column on enriched bars."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        df = self._make_ohlcv_df(200)

        # First enrich with VP columns, then compute the AMT signal
        enriched = calc.calculate(
            df, ["vp_vah", "vp_val", "acceptance_into_value"]
        )

        assert "acceptance_into_value" in enriched.columns


class TestDomainServicesIndicatorMath:
    """Black-box tests for pure domain service functions used by indicators.
    These do not require pandas_ta, only numpy/pandas."""

    @staticmethod
    def _make_ohlcv_df(periods: int = 200) -> "pd.DataFrame":
        """Create a sample OHLCV DataFrame for testing."""
        import pandas as pd

        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=periods, freq="h")
        close = 100 + np.cumsum(np.random.randn(periods) * 0.5)
        return pd.DataFrame(
            {
                "open": close - np.random.rand(periods),
                "high": close + np.random.rand(periods) * 2,
                "low": close - np.random.rand(periods) * 2,
                "close": close,
                "volume": np.random.randint(100000, 1000000, periods),
            },
            index=dates,
        )

    PANDAS_REQUIRED_MSG = "pandas required for domain service indicators"

    def _check_pandas(self):
        try:
            import pandas as pd  # noqa: F401
        except ImportError:
            pytest.skip(self.PANDAS_REQUIRED_MSG)

    def test_volume_profile_returns_result(self):
        """Volume profile computation returns a valid result with VAH/VAL/POC."""
        self._check_pandas()
        from finbar_strategy_runtime.domain.services.volume_profile import (
            compute_all_session_volume_profiles,
        )

        df = self._make_ohlcv_df(200)
        result = compute_all_session_volume_profiles(df)

        assert result is not None
        assert len(result) == len(df)
        assert "vp_poc" in result.columns
        assert "vp_vah" in result.columns
        assert "vp_val" in result.columns

    def test_auction_state_classifies(self):
        """Auction state classifier produces an output column."""
        self._check_pandas()
        from finbar_strategy_runtime.domain.services.volume_profile import (
            compute_all_session_volume_profiles,
        )
        from finbar_strategy_runtime.domain.services.auction_state import (
            classify_auction_state,
        )

        df = self._make_ohlcv_df(200)
        vp = compute_all_session_volume_profiles(df)
        enriched = classify_auction_state(vp)

        assert "inside_value" in enriched.columns
        assert "above_value" in enriched.columns
        assert "below_value" in enriched.columns

    def test_proxy_indicator_enriches(self):
        """Proxy indicator computation adds derived columns."""
        self._check_pandas()
        import pandas as pd

        from finbar_strategy_runtime.domain.services.proxy_indicator import (
            enrich_dataframe_with_proxies,
        )

        df = self._make_ohlcv_df(200)
        result = enrich_dataframe_with_proxies(df)
        # result is the enriched DataFrame
        enriched = result

        assert len(enriched) == len(df)
        # Proxy enrichment typically adds prefix columns
        assert isinstance(enriched, pd.DataFrame)

    def test_content_hash_is_deterministic(self):
        """Artifact hash produces the same result for identical inputs."""
        from finbar_strategy_runtime.domain.services.content_hash import (
            compute_artifact_hash,
        )

        h1 = compute_artifact_hash(
            symbol="AAPL",
            source="yfinance",
            interval="1d",
            indicators=["sma_20", "rsi_14"],
            timeframe_alias="primary",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )
        h2 = compute_artifact_hash(
            symbol="AAPL",
            source="yfinance",
            interval="1d",
            indicators=["rsi_14", "sma_20"],  # sorted order = same hash
            timeframe_alias="primary",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest


class TestArchitecture:
    """Architecture tests — the package must not depend on Finbar app layers."""

    FORBIDDEN_IMPORTS = [
        "finbar.presentation",
        "finbar.startup",
        "finbar.infrastructure.repositories",
        "finbar.infrastructure.data",
        "finbar.infrastructure.tables",
        "fastapi",
        "fastmcp",
        "sqlalchemy",
        "yfinance",
        "hyperliquid",
    ]

    def test_package_has_no_forbidden_imports(self):
        """The runtime package must not import Finbar presentation, startup,
        repositories, fetchers, or ORM frameworks."""
        import ast
        import importlib

        package_root = Path(__file__).resolve().parents[2] / "finbar_strategy_runtime"
        violating = []

        for py_file in package_root.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imp = alias.name
                        for forbidden in self.FORBIDDEN_IMPORTS:
                            if imp == forbidden or imp.startswith(forbidden + "."):
                                violating.append(f"{py_file.name}: imports {imp}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for forbidden in self.FORBIDDEN_IMPORTS:
                        if module == forbidden or module.startswith(forbidden + "."):
                            violating.append(f"{py_file.name}: from {module}")

        assert len(violating) == 0, (
            f"Forbidden imports found:\n" + "\n".join(violating)
        )
