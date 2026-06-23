"""Contract tests for the strategy runtime package — evaluation and risk."""

import pytest

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
    """Build a condition with a left column and right operand."""
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
    """Build a condition group."""
    return ConditionGroup(kind=kind, condition=condition, children=list(children))

# =========================================================================
# Scenario 2: Runtime package evaluates strategy conditions and risk prices
# =========================================================================

from finbar_strategy_runtime.domain.entities.condition import Condition
from finbar_strategy_runtime.domain.entities.condition_group import ConditionGroup
from finbar_strategy_runtime.domain.entities.operand import Operand

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


class TestCrossoverStateDuringPosition:
    """Regression: entry crossover state must not go stale during a position."""

    def test_entry_crossover_not_fired_with_stale_state(self):
        """After exiting a position, crossover should compare to the
        immediately preceding bar, not the bar before position entry."""
        entry = ConditionGroup(
            kind="condition",
            condition=Condition(
                left=Operand(kind="field", value="rsi", label="rsi"),
                operator="crosses_above",
                right=Operand(kind="literal", value=50, label="50"),
            ),
        )
        definition = StrategyDefinition(
            name="test",
            sides={
                "long": SideRules(
                    side="long", entry=entry, entry_confidence=1.0
                )
            },
        )
        strategy = JsonRuleBasedStrategy(definition)

        # Bar 0-1: flat, no position, entry crossover state tracked
        strategy.on_bar({"rsi": 40.0}, {"direction": "", "size": 0})
        strategy.on_bar({"rsi": 48.0}, {"direction": "", "size": 0})

        # Bars 2-6: in position, rsi goes 52→62→72→62→52
        for rsi in [52, 62, 72, 62, 52]:
            strategy.on_bar(
                {"rsi": float(rsi)}, {"direction": "long", "size": 1}
            )

        # Bar 7: position closed, rsi=72 (was already >50 in bar 6)
        # With stale state: prev=48 → 48<=50 and 72>50 → false crossover
        # With correct state: prev=52 → 52>50 → no crossover
        result = strategy.on_bar({"rsi": 72.0}, {"direction": "", "size": 0})
        assert result.action == "hold", (
            "False crossover fired: entry state was stale during position"
        )


