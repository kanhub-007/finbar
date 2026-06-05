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


def _make_use_case() -> BacktestStrategyDefinitionUseCase:
    return BacktestStrategyDefinitionUseCase(
        engine=BacktestRunner(),
        converter=PandasBarFrameConverter(),
        strategy_factory=StrategyDefinitionFactory(),
        parser=StrategyDefinitionParser(),
        timeframe_merger=PandasTimeframeBarMerger(),
    )


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
