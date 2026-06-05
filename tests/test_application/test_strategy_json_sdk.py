"""Tests for the v2 strategy JSON SDK application slice."""

from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
)
from finbar.core.application.services.strategy_definition_v2_parser import (
    StrategyDefinitionV2Parser,
)
from finbar.core.application.use_cases.backtest_strategy_definition import (
    BacktestStrategyDefinitionUseCase,
)
from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.json_strategy_definition_strategy_factory import (
    JsonStrategyDefinitionStrategyFactory,
)
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)


def _sma_strategy() -> dict:
    return {
        "schema_version": "2.0",
        "name": "agent_sma_cross",
        "description": "Long SMA crossover strategy.",
        "parameters": {
            "fast_period": {"type": "int", "default": 20, "minimum": 2, "maximum": 200},
            "slow_period": {"type": "int", "default": 50, "minimum": 2, "maximum": 200},
        },
        "indicators": [
            {"name": "fast_sma", "type": "sma", "period": "{{ fast_period }}"},
            {"name": "slow_sma", "type": "sma", "period": "{{ slow_period }}"},
        ],
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {
                                "left": "fast_sma",
                                "operator": "crosses_above",
                                "right": "slow_sma",
                            }
                        ]
                    }
                },
                "exit": {
                    "condition": {
                        "any": [
                            {
                                "left": "fast_sma",
                                "operator": "crosses_below",
                                "right": "slow_sma",
                            }
                        ]
                    }
                },
            }
        },
    }


def _bars_with_sma() -> list[dict]:
    return [
        {
            "timestamp": "2024-01-01",
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 1000,
            "sma_20": 99,
            "sma_50": 100,
        },
        {
            "timestamp": "2024-01-02",
            "open": 101,
            "high": 102,
            "low": 100,
            "close": 101,
            "volume": 1000,
            "sma_20": 101,
            "sma_50": 100,
        },
        {
            "timestamp": "2024-01-03",
            "open": 102,
            "high": 103,
            "low": 101,
            "close": 102,
            "volume": 1000,
            "sma_20": 102,
            "sma_50": 100,
        },
        {
            "timestamp": "2024-01-04",
            "open": 101,
            "high": 102,
            "low": 99,
            "close": 99,
            "volume": 1000,
            "sma_20": 99,
            "sma_50": 100,
        },
    ]


class TestStrategyJsonSdk:
    def test_parser_resolves_aliases_to_supported_concrete_indicators(self):
        result = StrategyDefinitionV2Parser().parse(_sma_strategy())

        assert result.valid is True
        assert result.required_indicators == ["sma_20", "sma_50"]
        assert result.required_columns == [
            "open",
            "high",
            "low",
            "close",
            "sma_20",
            "sma_50",
        ]
        assert result.definition is not None
        assert result.definition.indicators[0].name == "fast_sma"
        assert result.definition.indicators[0].concrete_name == "sma_20"

    def test_parser_rejects_unsupported_period_until_enrichment_supports_it(self):
        result = StrategyDefinitionV2Parser().parse(
            _sma_strategy(),
            {"fast_period": 37},
        )

        assert result.valid is False
        assert any(error.code == "unsupported_indicator" for error in result.errors)

    def test_backtest_requires_already_enriched_columns(self):
        use_case = _make_use_case()
        bars = [
            {
                "timestamp": "2024-01-01",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 1000,
            }
        ]

        result = use_case.execute(
            BacktestStrategyDefinitionRequest(
                definition=_sma_strategy(),
                bars=bars,
            )
        )

        assert result.valid is False
        assert result.missing_columns == ["sma_20", "sma_50"]
        assert any(error.code == "missing_columns" for error in result.errors)

    def test_backtest_runs_against_supplied_enriched_bars(self):
        use_case = _make_use_case()

        result = use_case.execute(
            BacktestStrategyDefinitionRequest(
                definition=_sma_strategy(),
                bars=_bars_with_sma(),
                symbol="TEST",
                interval="1d",
            )
        )

        assert result.valid is True
        assert result.result is not None
        assert result.result.error is None
        assert result.result.strategy_name == "agent_sma_cross"
        assert result.result.symbol == "TEST"
        assert result.result.interval == "1d"
        assert result.result.bar_count == 4
        assert result.result.total_trades == 1

    def test_crossover_state_updates_when_prior_all_condition_is_false(self):
        use_case = _make_use_case()
        bars = [
            _bar("2024-01-01", volume=100, sma_20=99, sma_50=100),
            _bar("2024-01-02", volume=2000, sma_20=101, sma_50=100),
            _bar("2024-01-03", volume=2000, sma_20=102, sma_50=100),
        ]

        result = use_case.execute(
            BacktestStrategyDefinitionRequest(
                definition=_volume_filtered_sma_strategy(),
                bars=bars,
            )
        )

        assert result.valid is True
        assert result.result is not None
        assert result.result.total_trades == 0
        assert result.result.equity_curve[-1]["position"] == 100

    def test_direct_concrete_indicator_operand_is_required_column(self):
        result = _make_use_case().execute(
            BacktestStrategyDefinitionRequest(
                definition=_direct_rsi_strategy(),
                bars=[_bar("2024-01-01")],
            )
        )

        assert result.valid is False
        assert result.missing_columns == ["rsi_14"]

    def test_field_operand_is_required_column(self):
        bar = _bar("2024-01-01")
        del bar["volume"]

        result = _make_use_case().execute(
            BacktestStrategyDefinitionRequest(
                definition=_volume_field_strategy(),
                bars=[bar],
            )
        )

        assert result.valid is False
        assert result.missing_columns == ["volume"]

    def test_fixed_indicator_rejects_custom_period_until_enrichment_supports_it(self):
        result = StrategyDefinitionV2Parser().parse(_atr_period_strategy())

        assert result.valid is False
        assert any(
            error.code == "unsupported_indicator_parameter" for error in result.errors
        )

    def test_invalid_parameter_bounds_return_structured_error(self):
        strategy = _sma_strategy()
        strategy["parameters"]["fast_period"]["minimum"] = "two"

        result = StrategyDefinitionV2Parser().parse(strategy)

        assert result.valid is False
        assert any(error.code == "invalid_parameter_bound" for error in result.errors)

    def test_short_side_strategy_can_enter_and_exit(self):
        bars = [
            _bar("2024-01-01", sma_20=101, sma_50=100),
            _bar("2024-01-02", sma_20=99, sma_50=100),
            _bar("2024-01-03", sma_20=98, sma_50=100),
            _bar("2024-01-04", sma_20=101, sma_50=100),
        ]

        result = _make_use_case().execute(
            BacktestStrategyDefinitionRequest(
                definition=_short_sma_strategy(),
                bars=bars,
            )
        )

        assert result.valid is True
        assert result.result is not None
        assert result.result.total_trades == 1
        assert result.result.trades[0]["metadata"]["direction"] == "short"


def _volume_filtered_sma_strategy() -> dict:
    strategy = _sma_strategy()
    strategy["name"] = "volume_filtered_sma"
    strategy["sides"]["long"]["entry"]["condition"] = {
        "all": [
            {"left": "volume", "operator": ">", "right": 1000},
            {"left": "fast_sma", "operator": "crosses_above", "right": "slow_sma"},
        ]
    }
    strategy["sides"]["long"].pop("exit")
    return strategy


def _direct_rsi_strategy() -> dict:
    return {
        "schema_version": "2.0",
        "name": "direct_rsi",
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {"left": "rsi_14", "operator": "<", "right": 30},
                        ]
                    }
                }
            }
        },
    }


def _volume_field_strategy() -> dict:
    return {
        "schema_version": "2.0",
        "name": "volume_filter",
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {"left": "volume", "operator": ">", "right": 1000},
                        ]
                    }
                }
            }
        },
    }


def _atr_period_strategy() -> dict:
    strategy = _sma_strategy()
    strategy["indicators"] = [
        {"name": "atr_fast", "type": "atr", "period": 20},
    ]
    strategy["sides"]["long"]["entry"]["condition"] = {
        "all": [{"left": "atr_fast", "operator": ">", "right": 1}]
    }
    return strategy


def _short_sma_strategy() -> dict:
    strategy = _sma_strategy()
    strategy["name"] = "short_sma_cross"
    strategy["sides"].pop("long")
    strategy["sides"]["short"] = {
        "entry": {
            "condition": {
                "all": [
                    {
                        "left": "fast_sma",
                        "operator": "crosses_below",
                        "right": "slow_sma",
                    }
                ]
            }
        },
        "exit": {
            "condition": {
                "any": [
                    {
                        "left": "fast_sma",
                        "operator": "crosses_above",
                        "right": "slow_sma",
                    }
                ]
            }
        },
    }
    return strategy


def _bar(
    timestamp: str,
    volume: int = 1000,
    sma_20: int | None = None,
    sma_50: int | None = None,
) -> dict:
    bar = {
        "timestamp": timestamp,
        "open": 100,
        "high": 101,
        "low": 99,
        "close": 100,
        "volume": volume,
    }
    if sma_20 is not None:
        bar["sma_20"] = sma_20
    if sma_50 is not None:
        bar["sma_50"] = sma_50
    return bar


def _make_use_case() -> BacktestStrategyDefinitionUseCase:
    return BacktestStrategyDefinitionUseCase(
        engine=BacktestRunner(),
        converter=PandasBarFrameConverter(),
        strategy_factory=JsonStrategyDefinitionStrategyFactory(),
    )
