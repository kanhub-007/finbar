"""Tests for warmup state preservation during backtests.

Ensures that warmup bars build crossover state without allowing trades,
so a crossover established on a warmup bar can trigger on the first
tradable bar.
"""

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


def _crossover_strategy() -> dict:
    """A strategy that enters long when fast crosses above slow, gated by filter.

    Uses three indicators with different periods so the warmup column
    (sma_5) differs from the crossover columns (sma_2, sma_3).
    """
    return {
        "schema_version": "2.0",
        "name": "warmup_crossover",
        "indicators": [
            {"name": "fast", "type": "sma", "period": 2},
            {"name": "slow", "type": "sma", "period": 3},
            {"name": "filter", "type": "sma", "period": 5},
        ],
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {
                                "operator": "crosses_above",
                                "left": "fast",
                                "right": "slow",
                            },
                            {"left": "filter", "operator": ">", "right": 0},
                        ]
                    }
                }
            }
        },
    }


def _make_use_case() -> BacktestStrategyDefinitionUseCase:
    return BacktestStrategyDefinitionUseCase(
        engine=BacktestRunner(),
        converter=PandasBarFrameConverter(),
        strategy_factory=StrategyDefinitionFactory(),
        parser=StrategyDefinitionParser(),
        timeframe_merger=PandasTimeframeBarMerger(),
    )


def _bar(timestamp, close, sma_2, sma_3, sma_5) -> dict:
    return {
        "timestamp": timestamp,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1000,
        "sma_2": sma_2,
        "sma_3": sma_3,
        "sma_5": sma_5,
    }


class TestWarmupStatePreservation:
    """Black-box tests: warmup bars build state but cannot trade."""

    def test_crossover_baseline_on_warmup_bar_triggers_on_first_tradable(self):
        """The crossover baseline (fast <= slow) is on the warmup bar.
        The first tradable bar has fast > slow, completing the crossover.
        Without warmup state, the strategy starts fresh on the tradable bar
        and misses the crossover entirely."""
        bars = [
            # warmup bar: sma_5 is NaN, but sma_2=90 <= sma_3=100 establishes
            # the crossover baseline
            _bar("2024-01-01", 100, 90.0, 100.0, float("nan")),
            # first tradable bar: sma_2=110 > sma_3=100, crossover completes
            _bar("2024-01-02", 100, 110.0, 100.0, 50.0),
            # entry fills on this bar's open
            _bar("2024-01-03", 110, 110.0, 100.0, 50.0),
        ]

        result = _make_use_case().execute(
            BacktestStrategyDefinitionRequest(
                definition=_crossover_strategy(),
                bars=bars,
                symbol="TEST",
                interval="1d",
            )
        )

        assert result.valid is True
        assert result.result is not None
        assert result.result.warmup_bars == 1
        # The crossover must fire because the warmup bar seeded the baseline
        assert result.result.total_trades == 1
        assert result.result.trades[0]["entry_date"] == "2024-01-03"

    def test_no_trade_opened_during_warmup(self):
        """Even if the entry condition is true during warmup, no trade opens."""
        strategy = {
            "schema_version": "2.0",
            "name": "warmup_no_trade",
            "indicators": [
                {"name": "fast", "type": "sma", "period": 2},
            ],
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "left": "fast",
                            "operator": ">",
                            "right": 0,
                        }
                    }
                }
            },
        }
        bars = [
            # warmup bar: indicator is NaN
            _bar("2024-01-01", 100, float("nan"), float("nan"), float("nan")),
            # first tradable bar: fast > 0 is true, signal queued
            _bar("2024-01-02", 100, 100.0, 100.0, 100.0),
            # entry fills on this bar's open
            _bar("2024-01-03", 100, 100.0, 100.0, 100.0),
        ]

        result = _make_use_case().execute(
            BacktestStrategyDefinitionRequest(
                definition=strategy,
                bars=bars,
                symbol="TEST",
                interval="1d",
            )
        )

        assert result.valid is True
        assert result.result.warmup_bars == 1
        # Entry fills on bar 2 open (2024-01-03), not during warmup
        assert result.result.trades[0]["entry_date"] == "2024-01-03"
