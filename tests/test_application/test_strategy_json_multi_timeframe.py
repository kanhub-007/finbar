"""Tests for multi-timeframe strategy JSON SDK support."""

import json
from pathlib import Path

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
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar.infrastructure.services.pandas_timeframe_bar_merger import (
    PandasTimeframeBarMerger,
)
from finbar.infrastructure.services.strategy_definition_factory import (
    StrategyDefinitionFactory,
)
from tests.fakes.fake_artifact_provider import FakeArtifactProvider


def test_parser_resolves_informative_indicator_to_suffixed_column():
    """Informative indicators resolve to columns suffixed by interval."""
    result = StrategyDefinitionParser().parse(_multi_timeframe_strategy())

    assert result.valid is True
    assert result.required_indicators == ["sma_50_1d", "vwap"]
    assert result.required_columns == [
        "open",
        "high",
        "low",
        "close",
        "sma_50_1d",
        "vwap",
    ]
    assert result.primary_required_indicators == ["vwap"]
    assert result.informative_required_indicators == {"daily": ["sma_50"]}
    assert result.timeframe_intervals == {"primary": "1h", "daily": "1d"}
    assert result.definition is not None
    assert result.definition.indicators[0].expected_column == "sma_50_1d"


def test_parser_rejects_unknown_timeframe_alias():
    """Indicators may only reference primary or declared informative aliases."""
    strategy = _multi_timeframe_strategy()
    strategy["indicators"][0]["timeframe"] = "weekly"

    result = StrategyDefinitionParser().parse(strategy)

    assert result.valid is False
    assert any(error.code == "unknown_timeframe" for error in result.errors)


def test_parser_rejects_duplicate_informative_intervals():
    """Duplicate informative intervals would collide in suffixed columns."""
    strategy = _multi_timeframe_strategy()
    strategy["timeframes"]["informative"].append(
        {"alias": "daily_again", "interval": "1d"}
    )

    result = StrategyDefinitionParser().parse(strategy)

    assert result.valid is False
    assert any(error.code == "duplicate_timeframe_interval" for error in result.errors)


def test_fixture_parses_successfully():
    """The tracked auction-drive approximation fixture parses successfully."""
    fixture = Path("tests/fixtures/strategies/multi_tf_auction_approx.json")
    strategy = json.loads(fixture.read_text())

    result = StrategyDefinitionParser().parse(strategy)

    assert result.valid is True
    assert result.informative_required_indicators["daily"] == [
        "sma_50",
        "sma_200",
    ]
    assert "sma_50_1d" in result.required_columns
    assert "sma_200_1d" in result.required_columns


def test_backtest_merges_informative_bars_before_execution():
    """Backtesting merges informative bars into primary bars before running."""
    result = _make_use_case().execute(
        BacktestStrategyDefinitionRequest(
            definition=_multi_timeframe_strategy(),
            bars=_primary_hourly_bars(),
            informative_bars={"daily": _daily_bars()},
            symbol="AAPL",
            interval="1h",
        )
    )

    assert result.valid is True
    assert result.result is not None
    assert result.result.error is None
    assert result.result.symbol == "AAPL"
    assert result.result.interval == "1h"


def test_backtest_requires_informative_bars_when_declared():
    """Missing informative bars return structured validation failure."""
    result = _make_use_case().execute(
        BacktestStrategyDefinitionRequest(
            definition=_multi_timeframe_strategy(),
            bars=_primary_hourly_bars(),
        )
    )

    assert result.valid is False
    assert any("Missing informative bars" in error.message for error in result.errors)


def test_backtest_does_not_leak_same_day_daily_bar_into_intraday():
    """Daily informative values are unavailable until the daily bar completes."""
    result = _make_use_case().execute(
        BacktestStrategyDefinitionRequest(
            definition=_daily_leak_probe_strategy(),
            bars=[
                _hourly_bar("2024-01-02T10:00:00", 100, 100),
                _hourly_bar("2024-01-02T11:00:00", 110, 100),
            ],
            informative_bars={
                "daily": [
                    {
                        "timestamp": "2024-01-02",
                        "open": 100,
                        "high": 101,
                        "low": 99,
                        "close": 100,
                        "volume": 10000,
                        "sma_50": 999,
                    }
                ]
            },
            symbol="AAPL",
            interval="1h",
        )
    )

    assert result.valid is True
    assert result.result is not None
    assert result.result.total_trades == 0
    assert result.result.final_value == 10000.0


def _make_use_case() -> BacktestStrategyDefinitionUseCase:
    return BacktestStrategyDefinitionUseCase(
        engine=BacktestRunner(),
        converter=PandasBarFrameConverter(),
        strategy_factory=StrategyDefinitionFactory(),
        parser=StrategyDefinitionParser(),
        timeframe_merger=PandasTimeframeBarMerger(),
    )


def _daily_leak_probe_strategy() -> dict:
    return {
        "schema_version": "2.0",
        "name": "daily_leak_probe",
        "timeframes": {
            "primary": "1h",
            "informative": [{"alias": "daily", "interval": "1d"}],
        },
        "indicators": [
            {
                "name": "daily_trend_sma",
                "type": "sma",
                "period": 50,
                "timeframe": "daily",
            }
        ],
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {
                                "left": "daily_trend_sma",
                                "operator": ">",
                                "right": 900,
                            },
                            {"left": "close", "operator": ">", "right": 0},
                        ]
                    }
                }
            }
        },
    }


def _multi_timeframe_strategy() -> dict:
    return {
        "schema_version": "2.0",
        "name": "mtf_trend_filter",
        "timeframes": {
            "primary": "1h",
            "informative": [{"alias": "daily", "interval": "1d"}],
        },
        "indicators": [
            {
                "name": "daily_trend_sma",
                "type": "sma",
                "period": 50,
                "timeframe": "daily",
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
                                "right": "daily_trend_sma",
                            },
                            {
                                "left": "close",
                                "operator": ">",
                                "right": "primary_vwap",
                            },
                        ]
                    }
                },
                "exit": {
                    "condition": {
                        "any": [
                            {
                                "left": "close",
                                "operator": "<",
                                "right": "primary_vwap",
                            }
                        ]
                    }
                },
            }
        },
    }


def _primary_hourly_bars() -> list[dict]:
    return [
        _hourly_bar("2024-01-02T10:00:00", 105, 100),
        _hourly_bar("2024-01-02T11:00:00", 106, 100),
        _hourly_bar("2024-01-03T10:00:00", 99, 100),
    ]


def _hourly_bar(timestamp: str, close: float, vwap: float) -> dict:
    return {
        "timestamp": timestamp,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 1000,
        "vwap": vwap,
    }


def _daily_bars() -> list[dict]:
    return [
        {
            "timestamp": "2024-01-02",
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 10000,
            "sma_50": 100,
        },
        {
            "timestamp": "2024-01-03",
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 10000,
            "sma_50": 100,
        },
    ]


def test_backtest_accepts_primary_bars_artifact_id():
    """A completed enrichment artifact can supply primary backtest bars."""
    use_case = _make_artifact_use_case(
        FakeArtifactProvider({"primary-job": _primary_hourly_bars()})
    )

    result = use_case.execute(
        BacktestStrategyDefinitionRequest(
            definition=_single_timeframe_strategy(),
            bars_artifact_id="primary-job",
            symbol="AAPL",
            interval="1h",
        )
    )

    assert result.valid is True
    assert result.result is not None
    assert result.result.error is None


def test_backtest_accepts_informative_artifact_ids():
    """Completed enrichment artifacts can supply informative timeframe bars."""
    provider = FakeArtifactProvider(
        {
            "primary-job": _primary_hourly_bars(),
            "daily-job": _daily_bars(),
        }
    )
    use_case = _make_artifact_use_case(provider)

    result = use_case.execute(
        BacktestStrategyDefinitionRequest(
            definition=_multi_timeframe_strategy(),
            bars_artifact_id="primary-job",
            informative_bars_artifact_ids={"daily": "daily-job"},
            symbol="AAPL",
            interval="1h",
        )
    )

    assert result.valid is True
    assert result.result is not None
    assert result.result.error is None


def test_backtest_rejects_incomplete_artifact_id():
    """Artifact-backed backtests require completed enrichment jobs."""
    provider = FakeArtifactProvider(
        {"primary-job": _primary_hourly_bars()},
        statuses={"primary-job": "running"},
    )
    use_case = _make_artifact_use_case(provider)

    result = use_case.execute(
        BacktestStrategyDefinitionRequest(
            definition=_single_timeframe_strategy(),
            bars_artifact_id="primary-job",
        )
    )

    assert result.valid is False
    assert any(error.code == "artifact_error" for error in result.errors)


def _make_artifact_use_case(provider) -> BacktestStrategyDefinitionUseCase:
    return BacktestStrategyDefinitionUseCase(
        engine=BacktestRunner(),
        converter=PandasBarFrameConverter(),
        strategy_factory=StrategyDefinitionFactory(),
        parser=StrategyDefinitionParser(),
        timeframe_merger=PandasTimeframeBarMerger(),
        artifact_provider=provider,
    )


def _single_timeframe_strategy() -> dict:
    return {
        "schema_version": "2.0",
        "name": "single_tf_vwap",
        "indicators": [{"name": "primary_vwap", "type": "vwap"}],
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {"left": "close", "operator": ">", "right": "primary_vwap"}
                        ]
                    }
                },
                "exit": {
                    "condition": {
                        "any": [
                            {"left": "close", "operator": "<", "right": "primary_vwap"}
                        ]
                    }
                },
            }
        },
    }
