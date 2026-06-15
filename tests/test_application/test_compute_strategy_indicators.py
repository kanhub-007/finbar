"""Tests for ComputeStrategyIndicatorsUseCase — timeframe interval routing."""

from finbar.core.application.services.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.application.use_cases.compute_strategy_indicators import (
    ComputeStrategyIndicatorsUseCase,
)
from finbar.core.domain.entities.indicator_job import IndicatorJob
from finbar.core.domain.interfaces.indicator_job_runner import IndicatorJobRunner
from finbar.core.domain.interfaces.indicator_job_manager import IndicatorJobManager
from tests.fakes.recording_indicator_job_manager import (
    RecordingIndicatorJobManager,
)


class _NoopIndicatorJobRunner(IndicatorJobRunner):
    """Runner that never executes; the recording manager never calls it."""

    async def run(self, job: IndicatorJob) -> None:
        """No-op."""


def _strategy_with_informative(alias: str, interval: str) -> str:
    """Build a valid MTF strategy with one informative timeframe."""
    import json

    definition = {
        "schema_version": "2.0",
        "name": f"mtf_{alias}",
        "timeframes": {
            "primary": "1d",
            "informative": [{"alias": alias, "interval": interval}],
        },
        "indicators": [
            {"name": f"{alias}_sma", "type": "sma", "period": 50, "timeframe": alias}
        ],
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "left": "close",
                        "operator": ">",
                        "right": f"{alias}_sma",
                    }
                }
            }
        },
    }
    return json.dumps(definition)


def _use_case(
    manager: IndicatorJobManager,
) -> ComputeStrategyIndicatorsUseCase:
    return ComputeStrategyIndicatorsUseCase(
        StrategyDefinitionParser(), manager, _NoopIndicatorJobRunner()
    )


class TestInformativeJobIntervals:
    """Black-box tests: the use case starts jobs with the right interval."""

    def test_weekly_informative_job_uses_declared_interval(self):
        """An informative timeframe declared as 1w must start a 1w job."""
        manager = RecordingIndicatorJobManager()

        result = _use_case(manager).execute(
            _strategy_with_informative(alias="weekly", interval="1w"),
            symbol="BTC",
            source="yfinance",
        )

        assert result.valid is True
        assert manager.started_params["primary"]["interval"] == "1d"
        assert manager.started_params["weekly"]["interval"] == "1w"

    def test_daily_informative_job_uses_declared_interval(self):
        """An informative timeframe declared as 1d must start a 1d job."""
        manager = RecordingIndicatorJobManager()

        result = _use_case(manager).execute(
            _strategy_with_informative(alias="daily", interval="1d"),
            symbol="BTC",
            source="yfinance",
        )

        assert result.valid is True
        assert manager.started_params["daily"]["interval"] == "1d"

    def test_multiple_informative_aliases_each_use_their_own_interval(self):
        """Multiple informative timeframes each route to their declared interval."""
        manager = RecordingIndicatorJobManager()
        import json

        definition = {
            "schema_version": "2.0",
            "name": "multi_mtf",
            "timeframes": {
                "primary": "1h",
                "informative": [
                    {"alias": "daily", "interval": "1d"},
                    {"alias": "weekly", "interval": "1w"},
                ],
            },
            "indicators": [
                {"name": "d_sma", "type": "sma", "period": 50, "timeframe": "daily"},
                {"name": "w_sma", "type": "sma", "period": 50, "timeframe": "weekly"},
            ],
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "all": [
                                {"left": "close", "operator": ">", "right": "d_sma"},
                                {"left": "close", "operator": ">", "right": "w_sma"},
                            ]
                        }
                    }
                }
            },
        }

        result = _use_case(manager).execute(
            json.dumps(definition), symbol="BTC", source="yfinance"
        )

        assert result.valid is True
        assert manager.started_params["primary"]["interval"] == "1h"
        assert manager.started_params["daily"]["interval"] == "1d"
        assert manager.started_params["weekly"]["interval"] == "1w"
