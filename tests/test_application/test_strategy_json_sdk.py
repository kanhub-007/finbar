"""Tests for the strategy JSON SDK application slice."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from finbar.core.application.dto.apply_strategy_features_request import (
    ApplyStrategyFeaturesRequest,
)
from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
)
from finbar.core.application.dto.save_strategy_definition_request import (
    SaveStrategyDefinitionRequest,
)
from finbar.core.application.services.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.application.use_cases.apply_strategy_features import (
    ApplyStrategyFeaturesUseCase,
)
from finbar.core.application.use_cases.backtest_strategy_definition import (
    BacktestStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.explain_strategy_definition import (
    ExplainStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.save_strategy_definition import (
    SaveStrategyDefinitionUseCase,
)
from finbar.infrastructure.data.connection import Base
from finbar.infrastructure.repositories.sql_strategy_document_repository import (
    SqlStrategyDocumentRepository,
)
from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar.infrastructure.services.pandas_strategy_feature_calculator import (
    PandasStrategyFeatureCalculator,
)
from finbar.infrastructure.services.strategy_definition_factory import (
    StrategyDefinitionFactory,
)
from finbar.infrastructure.tables.strategy_document import (
    StrategyDocument as OrmStrategyDoc,
)


@pytest.fixture
def mem_db():
    """Create an in-memory SQLite database for strategy document tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[OrmStrategyDoc.__table__])
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


def _make_save_use_case(db) -> SaveStrategyDefinitionUseCase:
    return SaveStrategyDefinitionUseCase(SqlStrategyDocumentRepository(db))


def _sma_json_str() -> str:
    return json.dumps(
        {
            "schema_version": "2.0",
            "name": "persisted_sma_cross",
            "parameters": {
                "fast_period": {
                    "type": "int",
                    "default": 20,
                    "minimum": 2,
                    "maximum": 200,
                },
                "slow_period": {
                    "type": "int",
                    "default": 50,
                    "minimum": 2,
                    "maximum": 200,
                },
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
                    }
                }
            },
        }
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
        result = StrategyDefinitionParser().parse(_sma_strategy())

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
        result = StrategyDefinitionParser().parse(
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
        result = StrategyDefinitionParser().parse(_atr_period_strategy())

        assert result.valid is False
        assert any(
            error.code == "unsupported_indicator_parameter" for error in result.errors
        )

    def test_invalid_parameter_bounds_return_structured_error(self):
        strategy = _sma_strategy()
        strategy["parameters"]["fast_period"]["minimum"] = "two"

        result = StrategyDefinitionParser().parse(strategy)

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

    def test_strategy_feature_calculator_excludes_current_bar_with_shift(self):
        result = _make_feature_use_case().execute(
            ApplyStrategyFeaturesRequest(
                definition=_momentum_breakout_strategy(),
                bars=_momentum_bars(),
            )
        )

        assert result.error is None
        assert result.features_applied == ["prior_high"]
        assert result.bars[2]["prior_high"] == 11

    def test_momentum_breakout_feature_and_atr_stop_backtest(self):
        feature_result = _make_feature_use_case().execute(
            ApplyStrategyFeaturesRequest(
                definition=_momentum_breakout_strategy(),
                bars=_momentum_bars(),
            )
        )

        result = _make_use_case().execute(
            BacktestStrategyDefinitionRequest(
                definition=_momentum_breakout_strategy(),
                bars=feature_result.bars,
            )
        )

        assert result.valid is True
        assert result.result is not None
        assert result.result.total_trades == 1
        trade = result.result.trades[0]
        assert trade["entry_price"] == 12
        assert trade["exit_price"] == 10

    def test_invalid_risk_multiplier_returns_structured_error(self):
        strategy = _momentum_breakout_strategy()
        strategy["risk"]["stop_loss"]["multiplier"] = "two"

        result = StrategyDefinitionParser().parse(strategy)

        assert result.valid is False
        assert any(error.code == "invalid_risk_parameter" for error in result.errors)

    def test_negative_risk_multiplier_is_rejected(self):
        strategy = _momentum_breakout_strategy()
        strategy["risk"]["stop_loss"]["multiplier"] = -1

        result = StrategyDefinitionParser().parse(strategy)

        assert result.valid is False
        assert any(error.code == "invalid_risk_parameter" for error in result.errors)

    def test_unknown_risk_indicator_is_rejected(self):
        strategy = _momentum_breakout_strategy()
        strategy["risk"]["stop_loss"]["indicator"] = "atr_999"

        result = StrategyDefinitionParser().parse(strategy)

        assert result.valid is False
        assert any(error.code == "unknown_risk_indicator" for error in result.errors)

    def test_backtest_requires_feature_output_not_feature_source(self):
        bars = [_bar("2024-01-01"), _bar("2024-01-02")]
        for bar in bars:
            bar["volume_signal"] = 1
            del bar["volume"]

        result = _make_use_case().execute(
            BacktestStrategyDefinitionRequest(
                definition=_volume_feature_strategy(),
                bars=bars,
            )
        )

        assert result.valid is True
        assert result.result is not None
        assert result.result.error is None

    def test_apply_strategy_features_requires_feature_source_columns(self):
        bars = [dict(bar) for bar in _momentum_bars()]
        for bar in bars:
            del bar["high"]

        result = _make_feature_use_case().execute(
            ApplyStrategyFeaturesRequest(
                definition=_momentum_breakout_strategy(),
                bars=bars,
            )
        )

        assert result.error is not None
        assert any(error.code == "missing_columns" for error in result.errors)

    def test_risk_reward_target_exits_at_expected_price(self):
        result = _make_use_case().execute(
            BacktestStrategyDefinitionRequest(
                definition=_risk_reward_strategy(),
                bars=_risk_reward_bars(),
            )
        )

        assert result.valid is True
        assert result.result is not None
        assert result.result.total_trades == 1
        assert result.result.trades[0]["exit_price"] == 12


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


def _volume_feature_strategy() -> dict:
    strategy = _momentum_breakout_strategy()
    strategy["features"] = [
        {
            "name": "volume_signal",
            "type": "rolling_mean",
            "source": "volume",
            "window": 2,
        }
    ]
    strategy.pop("risk")
    strategy["sides"]["long"]["entry"]["condition"] = {
        "all": [{"left": "volume_signal", "operator": ">", "right": 0}]
    }
    return strategy


def _momentum_breakout_strategy() -> dict:
    return {
        "schema_version": "2.0",
        "name": "momentum_breakout_v2",
        "features": [
            {
                "name": "prior_high",
                "type": "rolling_max",
                "source": "high",
                "window": 2,
                "shift": 1,
            }
        ],
        "risk": {"stop_loss": {"type": "atr", "indicator": "atr", "multiplier": 2.0}},
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {"left": "close", "operator": ">", "right": "prior_high"}
                        ]
                    }
                }
            }
        },
    }


def _momentum_bars() -> list[dict]:
    return [
        _bar("2024-01-01", open_price=9, high=10, low=8, close=9, atr=1),
        _bar("2024-01-02", open_price=10, high=11, low=9, close=10, atr=1),
        _bar("2024-01-03", open_price=12, high=12, low=11, close=12, atr=1),
        _bar("2024-01-04", open_price=12, high=13, low=9, close=10, atr=1),
    ]


def _risk_reward_strategy() -> dict:
    strategy = _momentum_breakout_strategy()
    strategy["risk"] = {
        "stop_loss": {"type": "fixed_pct", "pct": 0.1},
        "take_profit": {"type": "risk_reward", "ratio": 2.0},
    }
    strategy["features"] = []
    strategy["sides"]["long"]["entry"]["condition"] = {
        "all": [{"left": "close", "operator": ">", "right": 1}]
    }
    return strategy


def _risk_reward_bars() -> list[dict]:
    return [
        _bar("2024-01-01", open_price=10, high=11, low=9, close=10),
        _bar("2024-01-02", open_price=10, high=14, low=10, close=14),
    ]


def _bar(
    timestamp: str,
    volume: int = 1000,
    sma_20: int | None = None,
    sma_50: int | None = None,
    open_price: int = 100,
    high: int = 101,
    low: int = 99,
    close: int = 100,
    atr: int | None = None,
    rsi_14: int | None = None,
) -> dict:
    bar = {
        "timestamp": timestamp,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }
    if sma_20 is not None:
        bar["sma_20"] = sma_20
    if sma_50 is not None:
        bar["sma_50"] = sma_50
    if atr is not None:
        bar["atr"] = atr
    if rsi_14 is not None:
        bar["rsi_14"] = rsi_14
    return bar


def _make_feature_use_case() -> ApplyStrategyFeaturesUseCase:
    return ApplyStrategyFeaturesUseCase(
        converter=PandasBarFrameConverter(),
        feature_calculator=PandasStrategyFeatureCalculator(),
    )


def _make_use_case() -> BacktestStrategyDefinitionUseCase:
    return BacktestStrategyDefinitionUseCase(
        engine=BacktestRunner(),
        converter=PandasBarFrameConverter(),
        strategy_factory=StrategyDefinitionFactory(),
    )


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _summary_bar(**overrides) -> dict:
    bar = {
        "timestamp": "2024-01-01",
        "open": 100,
        "high": 101,
        "low": 99,
        "close": 100,
        "volume": 1000,
        "sma_20": 101,
        "sma_50": 100,
    }
    bar.update(overrides)
    return bar


class TestStrategyPersistence:
    def test_save_valid_strategy(self, mem_db):
        result = _make_save_use_case(mem_db).execute(
            SaveStrategyDefinitionRequest(definition_json=_sma_json_str())
        )
        assert result.saved is True
        assert result.name == "persisted_sma_cross"
        assert result.schema_version == "2.0"
        assert result.error == ""

    def test_save_invalid_strategy_returns_errors(self, mem_db):
        bad_json = json.dumps({"schema_version": "2.0", "name": "bad"})
        result = _make_save_use_case(mem_db).execute(
            SaveStrategyDefinitionRequest(definition_json=bad_json)
        )
        assert result.saved is False
        assert len(result.validation_errors) > 0

    def test_save_duplicate_name_updates(self, mem_db):
        use_case = _make_save_use_case(mem_db)
        first = use_case.execute(
            SaveStrategyDefinitionRequest(definition_json=_sma_json_str())
        )
        assert first.saved is True

        second = use_case.execute(
            SaveStrategyDefinitionRequest(definition_json=_sma_json_str())
        )
        assert second.saved is True
        assert second.name == "persisted_sma_cross"

    def test_retrieve_after_save(self, mem_db):
        use_case = _make_save_use_case(mem_db)
        use_case.execute(SaveStrategyDefinitionRequest(definition_json=_sma_json_str()))
        doc = SqlStrategyDocumentRepository(mem_db).find_by_name("persisted_sma_cross")
        assert doc is not None
        assert doc.schema_version == "2.0"
        assert "fast_sma" in doc.definition_json

    def test_delete_after_save(self, mem_db):
        use_case = _make_save_use_case(mem_db)
        use_case.execute(SaveStrategyDefinitionRequest(definition_json=_sma_json_str()))
        repo = SqlStrategyDocumentRepository(mem_db)
        assert repo.delete("persisted_sma_cross") is True
        assert repo.find_by_name("persisted_sma_cross") is None

    def test_backtest_by_name_after_save(self, mem_db):
        use_case = _make_save_use_case(mem_db)
        use_case.execute(SaveStrategyDefinitionRequest(definition_json=_sma_json_str()))

        from finbar.core.application.services.strategy_definition_parser import (
            StrategyDefinitionParser,
        )
        from finbar.core.domain.entities.strategy_meta import DataMode
        from finbar.infrastructure.services.database_strategy_provider import (
            DatabaseStrategyProvider,
        )

        provider = DatabaseStrategyProvider(
            SqlStrategyDocumentRepository(mem_db),
            parser=StrategyDefinitionParser(),
        )
        strategy = provider.create("persisted_sma_cross")
        assert strategy is not None

        meta = strategy.meta()
        assert meta.name == "persisted_sma_cross"
        assert meta.variant == DataMode.REAL
        assert "sma_20" in meta.required_indicators
        assert "sma_50" in meta.required_indicators

        strategy.on_reset()

        bar_before = _summary_bar(sma_20=99, sma_50=100)
        assert strategy.on_bar(bar_before, {}).action == "hold"

        bar_cross = _summary_bar(sma_20=101, sma_50=100)
        signal = strategy.on_bar(bar_cross, {})
        assert signal.action == "buy"
        assert signal.direction == "long"

    def test_list_includes_v2_entries(self, mem_db):
        use_case = _make_save_use_case(mem_db)
        use_case.execute(SaveStrategyDefinitionRequest(definition_json=_sma_json_str()))
        docs = SqlStrategyDocumentRepository(mem_db).list_all()
        assert len(docs) == 1
        assert docs[0].name == "persisted_sma_cross"
        assert docs[0].schema_version == "2.0"


class TestSignalParity:
    def _make_json_strategy(self, definition: dict):
        factory = StrategyDefinitionFactory()
        parser = StrategyDefinitionParser()
        result = parser.parse(definition)
        assert result.valid and result.definition is not None
        return factory.create(result.definition)

    def _sma_crossover_v2(self) -> dict:
        return {
            "schema_version": "2.0",
            "name": "sma_parity",
            "parameters": {
                "fast_period": {
                    "type": "int",
                    "default": 20,
                    "minimum": 2,
                    "maximum": 200,
                },
                "slow_period": {
                    "type": "int",
                    "default": 50,
                    "minimum": 2,
                    "maximum": 200,
                },
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
                },
                "short": {
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
                },
            },
        }

    def _rsi_reversion_v2(self, oversold: int = 30, overbought: int = 70) -> dict:
        return {
            "schema_version": "2.0",
            "name": "rsi_parity",
            "parameters": {
                "rsi_period": {
                    "type": "int",
                    "default": 14,
                    "minimum": 2,
                    "maximum": 100,
                },
                "oversold": {
                    "type": "float",
                    "default": oversold,
                    "minimum": 1,
                    "maximum": 50,
                },
                "overbought": {
                    "type": "float",
                    "default": overbought,
                    "minimum": 50,
                    "maximum": 99,
                },
            },
            "indicators": [
                {"name": "rsi", "type": "rsi", "period": "{{ rsi_period }}"},
            ],
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "all": [
                                {
                                    "left": "rsi",
                                    "operator": "<",
                                    "right": "{{ oversold }}",
                                }
                            ]
                        }
                    },
                    "exit": {
                        "condition": {
                            "any": [
                                {
                                    "left": "rsi",
                                    "operator": ">",
                                    "right": "{{ overbought }}",
                                }
                            ]
                        }
                    },
                },
                "short": {
                    "entry": {
                        "condition": {
                            "all": [
                                {
                                    "left": "rsi",
                                    "operator": ">",
                                    "right": "{{ overbought }}",
                                }
                            ]
                        }
                    },
                    "exit": {
                        "condition": {
                            "any": [
                                {
                                    "left": "rsi",
                                    "operator": "<",
                                    "right": "{{ oversold }}",
                                }
                            ]
                        }
                    },
                },
            },
        }

    def test_sma_crossover_long_entry_parity(self):
        from finbar.infrastructure.services.backtest_strategies.sma_crossover import (
            SmaCrossoverStrategy,
        )

        json_strategy = self._make_json_strategy(self._sma_crossover_v2())
        builtin = SmaCrossoverStrategy(fast_period=20, slow_period=50)
        json_strategy.on_reset()
        builtin.on_reset()

        bars = [
            _bar("day1", sma_20=100, sma_50=101),
            _bar("day2", sma_20=100, sma_50=100),
            _bar("day3", sma_20=102, sma_50=100),
        ]

        for bar in bars:
            json_sig = json_strategy.on_bar(bar, {})
            builtin_sig = builtin.on_bar(bar, {})
            assert json_sig.action == builtin_sig.action, f'bar {bar["timestamp"]}'

            assert json_sig.direction == builtin_sig.direction

    def test_sma_crossover_long_exit_parity(self):
        from finbar.infrastructure.services.backtest_strategies.sma_crossover import (
            SmaCrossoverStrategy,
        )

        json_strategy = self._make_json_strategy(self._sma_crossover_v2())
        builtin = SmaCrossoverStrategy(fast_period=20, slow_period=50)
        json_strategy.on_reset()
        builtin.on_reset()

        bars = [
            _bar("day1", sma_20=102, sma_50=100),
            _bar("day2", sma_20=103, sma_50=100),
            _bar("day3", sma_20=99, sma_50=101),
        ]

        for i, bar in enumerate(bars):
            pos = {"size": 100, "direction": "long"} if i >= 1 else {}
            json_sig = json_strategy.on_bar(bar, pos)
            builtin_sig = builtin.on_bar(bar, pos)
            assert json_sig.action == builtin_sig.action, f'bar {bar["timestamp"]}'

            assert json_sig.direction == builtin_sig.direction

    def test_sma_crossover_short_entry_parity(self):
        from finbar.infrastructure.services.backtest_strategies.sma_crossover import (
            SmaCrossoverStrategy,
        )

        json_strategy = self._make_json_strategy(self._sma_crossover_v2())
        builtin = SmaCrossoverStrategy(fast_period=20, slow_period=50)
        json_strategy.on_reset()
        builtin.on_reset()

        bars = [
            _bar("day1", sma_20=101, sma_50=100),
            _bar("day2", sma_20=101, sma_50=100),
            _bar("day3", sma_20=98, sma_50=100),
        ]

        for bar in bars:
            json_sig = json_strategy.on_bar(bar, {})
            builtin_sig = builtin.on_bar(bar, {})
            assert json_sig.action == builtin_sig.action, f'bar {bar["timestamp"]}'

            assert json_sig.direction == builtin_sig.direction

    def test_rsi_mean_reversion_long_entry_parity(self):
        from finbar.infrastructure.services.backtest_strategies.rsi_mean_reversion import (  # noqa: E501
            RsiMeanReversionStrategy,
        )

        json_strategy = self._make_json_strategy(self._rsi_reversion_v2())
        builtin = RsiMeanReversionStrategy(rsi_period=14, oversold=30, overbought=70)
        json_strategy.on_reset()
        builtin.on_reset()

        bars = [
            _bar("day1", rsi_14=50),
            _bar("day2", rsi_14=25),
            _bar("day3", rsi_14=75),
        ]

        pos = {}
        for bar in bars:
            json_sig = json_strategy.on_bar(bar, pos)
            builtin_sig = builtin.on_bar(bar, pos)
            assert json_sig.action == builtin_sig.action, f"bar {bar['timestamp']}"
            assert json_sig.direction == builtin_sig.direction
            if builtin_sig.action == "buy" and builtin_sig.direction == "long":
                pos = {"size": 100, "direction": "long"}

    def test_rsi_mean_reversion_long_exit_parity(self):
        from finbar.infrastructure.services.backtest_strategies.rsi_mean_reversion import (  # noqa: E501
            RsiMeanReversionStrategy,
        )

        json_strategy = self._make_json_strategy(self._rsi_reversion_v2())
        builtin = RsiMeanReversionStrategy(rsi_period=14, oversold=30, overbought=70)
        json_strategy.on_reset()
        builtin.on_reset()

        bars = [
            _bar("day1", rsi_14=25),
            _bar("day2", rsi_14=80),
        ]

        pos = {"size": 100, "direction": "long"}
        for bar in bars:
            json_sig = json_strategy.on_bar(bar, pos)
            builtin_sig = builtin.on_bar(bar, pos)
            assert json_sig.action == builtin_sig.action, f"bar {bar['timestamp']}"
            assert json_sig.direction == builtin_sig.direction

    def test_flat_strategy_stays_hold(self):
        json_strategy = self._make_json_strategy(self._sma_crossover_v2())
        json_strategy.on_reset()
        bars = [
            _bar("day1", sma_20=100, sma_50=100),
            _bar("day2", sma_20=100, sma_50=100),
            _bar("day3", sma_20=100, sma_50=100),
        ]
        for bar in bars:
            assert json_strategy.on_bar(bar, {}).action == "hold"


class TestValidationWarningsAndLimits:
    def test_warns_when_no_exit_defined(self):
        strategy = _sma_strategy()
        strategy["sides"]["long"].pop("exit", None)
        result = StrategyDefinitionParser().parse(strategy)
        assert result.valid is True
        assert any(w.code == "no_exit" for w in result.warnings)

    def test_warns_when_no_stop_defined(self):
        result = StrategyDefinitionParser().parse(_sma_strategy())
        assert result.valid is True
        assert any(w.code == "no_stop" for w in result.warnings)

    def test_warns_on_both_no_exit_and_no_stop(self):
        strategy = _sma_strategy()
        strategy["sides"]["long"].pop("exit", None)
        result = StrategyDefinitionParser().parse(strategy)
        codes = {w.code for w in result.warnings}
        assert "no_exit" in codes
        assert "no_stop" in codes

    def test_limits_max_indicators_rejected(self):
        strategy = _sma_strategy()
        strategy["indicators"] = [
            {"name": "fast_sma", "type": "sma", "period": "{{ fast_period }}"},
            {"name": "slow_sma", "type": "sma", "period": "{{ slow_period }}"},
        ] + [
            {"name": f"ind_{i}", "type": "sma", "period": "{{ fast_period }}"}
            for i in range(19)
        ]
        strategy["sides"]["long"]["entry"]["condition"] = {
            "all": [{"left": "fast_sma", "operator": ">", "right": "slow_sma"}]
        }
        result = StrategyDefinitionParser().parse(strategy)
        assert result.valid is False
        assert any(
            "max" in e.message.lower() and "20" in e.message for e in result.errors
        )

    def test_limits_max_condition_depth_rejected(self):
        strategy = _sma_strategy()
        nested: dict = {"all": [{"left": "close", "operator": ">", "right": 1}]}
        for _ in range(6):
            nested = {"all": [nested]}
        strategy["sides"]["long"]["entry"]["condition"] = nested
        result = StrategyDefinitionParser().parse(strategy)
        assert result.valid is False
        assert any("max depth" in e.message.lower() for e in result.errors)

    def test_explainer_includes_risk_when_defined(self):
        strategy = _momentum_breakout_strategy()
        result = ExplainStrategyDefinitionUseCase().execute(strategy)
        assert result["valid"] is True
        assert "Stop-loss: ATR" in result["explanation"]

    def test_explainer_includes_features_when_defined(self):
        strategy = _momentum_breakout_strategy()
        result = ExplainStrategyDefinitionUseCase().execute(strategy)
        assert result["valid"] is True
        assert "rolling_max" in result["explanation"]

    def test_explainer_includes_warnings(self):
        strategy = _sma_strategy()
        strategy["sides"]["long"].pop("exit", None)
        result = ExplainStrategyDefinitionUseCase().execute(strategy)
        assert result["valid"] is True
        assert "no exit condition" in result["explanation"].lower()

    def test_explainer_includes_required_indicators(self):
        result = ExplainStrategyDefinitionUseCase().execute(_sma_strategy())
        assert result["valid"] is True
        assert "sma_20" in result["explanation"]
        assert "sma_50" in result["explanation"]

    def test_explainer_handles_invalid_strategy(self):
        result = ExplainStrategyDefinitionUseCase().execute(
            json.dumps({"schema_version": "2.0", "name": "bad"})
        )
        assert result["valid"] is False
        assert "invalid" in result["explanation"].lower()
