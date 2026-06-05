"""Tests for fallback indicator resolution and evaluation."""

from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
)
from finbar.core.application.services.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.application.use_cases.backtest_strategy_definition import (
    BacktestStrategyDefinitionUseCase,
)
from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.condition_evaluator import ConditionEvaluator
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar.infrastructure.services.strategy_definition_factory import (
    StrategyDefinitionFactory,
)


def _fallback_strategy() -> dict:
    return {
        "schema_version": "2.0",
        "name": "fallback_test",
        "indicators": [
            {
                "name": "effective_atr",
                "type": "fallback",
                "sources": ["atr_1d", "atr"],
            },
            {"name": "primary_vwap", "type": "vwap"},
        ],
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {
                                "left": "close",
                                "operator": ">",
                                "right": "effective_atr",
                            },
                            {
                                "left": "close",
                                "operator": ">",
                                "right": "primary_vwap",
                            },
                        ]
                    }
                }
            }
        },
    }


class TestFallbackIndicatorParsing:
    def test_fallback_strategy_parses(self):
        result = StrategyDefinitionParser().parse(_fallback_strategy())

        assert result.valid is True
        assert result.required_indicators == ["atr_1d", "vwap"]
        assert result.required_columns == [
            "open",
            "high",
            "low",
            "close",
            "atr_1d",
            "vwap",
        ]

    def test_fallback_indicator_stores_sources(self):
        result = StrategyDefinitionParser().parse(_fallback_strategy())

        spec = result.definition.indicators[0]
        assert spec.type == "fallback"
        assert spec.concrete_name == "atr_1d"
        assert "atr" in spec.sources

    def test_fallback_requires_at_least_two_sources(self):
        strategy = {
            "schema_version": "2.0",
            "name": "bad",
            "indicators": [{"name": "x", "type": "fallback", "sources": ["atr"]}],
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "all": [{"left": "close", "operator": ">", "right": "x"}]
                        }
                    }
                }
            },
        }
        result = StrategyDefinitionParser().parse(strategy)
        assert result.valid is False
        assert any("at least 2 sources" in e.message for e in result.errors)

    def test_fallback_rejects_unknown_source(self):
        strategy = {
            "schema_version": "2.0",
            "name": "bad",
            "indicators": [
                {"name": "x", "type": "fallback", "sources": ["atr", "nonexistent"]}
            ],
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "all": [{"left": "close", "operator": ">", "right": "x"}]
                        }
                    }
                }
            },
        }
        result = StrategyDefinitionParser().parse(strategy)
        assert result.valid is False
        assert any(e.code == "unsupported_indicator" for e in result.errors)


class TestFallbackConditionEvaluation:
    def test_evaluator_falls_back_when_primary_is_none(self):
        """Evaluator uses fallback source when primary is None in bar."""
        from finbar.core.domain.entities.condition import Condition
        from finbar.core.domain.entities.condition_group import ConditionGroup
        from finbar.core.domain.entities.operand import Operand

        bar = {"atr_1d": None, "atr": 5.0}
        condition = Condition(
            left=Operand(
                kind="indicator", value="atr_1d", label="eff", sources=["atr"]
            ),
            operator="<",
            right=Operand(kind="literal", value=10),
        )
        group = ConditionGroup(kind="condition", condition=condition)

        # atr_1d is None → fallback to atr=5.0. 5.0 < 10 → True.
        assert ConditionEvaluator().evaluate(group, bar, {}) is True

    def test_evaluator_uses_primary_when_present(self):
        """Evaluator uses primary source, not fallback, when primary exists."""
        from finbar.core.domain.entities.condition import Condition
        from finbar.core.domain.entities.condition_group import ConditionGroup
        from finbar.core.domain.entities.operand import Operand

        bar = {"atr_1d": 3.0, "atr": 5.0}
        condition = Condition(
            left=Operand(
                kind="indicator", value="atr_1d", label="eff", sources=["atr"]
            ),
            operator=">",
            right=Operand(kind="literal", value=5),
        )
        group = ConditionGroup(kind="condition", condition=condition)

        # atr_1d=3.0 (primary). 3.0 > 5 → False.
        assert ConditionEvaluator().evaluate(group, bar, {}) is False

    def test_evaluator_falls_back_when_primary_is_nan(self):
        """Evaluator falls back when primary source is float NaN."""
        from finbar.core.domain.entities.condition import Condition
        from finbar.core.domain.entities.condition_group import ConditionGroup
        from finbar.core.domain.entities.operand import Operand

        bar = {"atr_1d": float("nan"), "atr": 5.0}
        condition = Condition(
            left=Operand(
                kind="indicator", value="atr_1d", label="eff", sources=["atr"]
            ),
            operator="<",
            right=Operand(kind="literal", value=10),
        )
        group = ConditionGroup(kind="condition", condition=condition)

        # atr_1d=NaN → fallback to atr=5.0. 5.0 < 10 → True.
        assert ConditionEvaluator().evaluate(group, bar, {}) is True


class TestFallbackBacktest:
    def test_backtest_with_primary_source_only(self):
        bars = _bars_with_atr_1d()
        use_case = BacktestStrategyDefinitionUseCase(
            engine=BacktestRunner(),
            converter=PandasBarFrameConverter(),
            strategy_factory=StrategyDefinitionFactory(),
            parser=StrategyDefinitionParser(),
        )
        result = use_case.execute(
            BacktestStrategyDefinitionRequest(
                definition=_fallback_strategy(), bars=bars, symbol="AAPL", interval="1h"
            )
        )
        assert result.valid is True
        assert result.result is not None


def _bars_with_atr_1d() -> list[dict]:
    return [
        {
            "timestamp": "2024-01-01T10:00:00",
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 1000,
            "atr_1d": 5.0,
            "vwap": 99,
        },
        {
            "timestamp": "2024-01-01T11:00:00",
            "open": 105,
            "high": 106,
            "low": 104,
            "close": 105,
            "volume": 1000,
            "atr_1d": 5.0,
            "vwap": 103,
        },
        {
            "timestamp": "2024-01-01T12:00:00",
            "open": 102,
            "high": 103,
            "low": 101,
            "close": 102,
            "volume": 1000,
            "atr_1d": 5.0,
            "vwap": 103,
        },
    ]
