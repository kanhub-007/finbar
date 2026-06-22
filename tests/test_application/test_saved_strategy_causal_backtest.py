"""Tests for saved JSON strategies using causal package enrichment.

Scenario 12: a saved/named JSON strategy backtest must consume the same causal
streaming enricher as the inline JSON backtest path.
"""

from __future__ import annotations

from finbar_strategy_runtime.domain.entities.strategy_kind import StrategyKind
from finbar_strategy_runtime.domain.interfaces.trading_strategy import TradingStrategy
from finbar_strategy_runtime.indicators.multi_timeframe_bar_enricher import (
    MultiTimeframeBarEnricher,
)
from finbar_strategy_runtime.indicators.pandas_strategy_feature_calculator import (
    PandasStrategyFeatureCalculator,
)
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)
from finbar_strategy_runtime.indicators.pandas_timeframe_bar_merger import (
    PandasTimeframeBarMerger,
)

from finbar.core.application.dto.backtest_request import BacktestRequest
from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
)
from finbar.core.application.services.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.application.use_cases.backtest_strategy_definition import (
    BacktestStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.run_backtest import RunBacktestUseCase
from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.strategy_provider import StrategyProvider
from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar.infrastructure.services.strategy_definition_factory import (
    StrategyDefinitionFactory,
)


def _bars(count: int = 80) -> list[dict]:
    """Return deterministic timestamped OHLCV bars."""
    return [
        {
            "timestamp": f"2026-02-{(i // 24) + 1:02d}T{i % 24:02d}:00:00Z",
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 1000.0 + (i * 10.0),
        }
        for i in range(count)
    ]


def _vwap_strategy() -> dict:
    """Return a saved-compatible strategy requiring causal vwap enrichment."""
    return {
        "schema_version": "2.0",
        "name": "saved_vwap_strategy",
        "indicators": [{"name": "primary_vwap", "type": "vwap"}],
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {
                                "left": "close",
                                "operator": ">",
                                "right": "primary_vwap",
                            }
                        ]
                    }
                }
            }
        },
    }


def _enricher() -> MultiTimeframeBarEnricher:
    """Create the package batch enricher dependency for the use cases."""
    return MultiTimeframeBarEnricher(
        indicator_calculator=PandasTaIndicatorCalculator(),
        bar_converter=PandasBarFrameConverter(),
        timeframe_merger=PandasTimeframeBarMerger(),
        feature_calculator=PandasStrategyFeatureCalculator(),
    )


def _inline_use_case() -> BacktestStrategyDefinitionUseCase:
    """Create the inline JSON backtest use case."""
    return BacktestStrategyDefinitionUseCase(
        engine=BacktestRunner(),
        converter=PandasBarFrameConverter(),
        strategy_factory=StrategyDefinitionFactory(),
        parser=StrategyDefinitionParser(),
        enricher=_enricher(),
    )


class SavedJsonStrategyProvider(StrategyProvider):
    """In-memory saved strategy provider for application tests."""

    def __init__(self, definition: dict):
        """Store a single saved definition."""
        self._definition = definition

    def create(self, name: str, params: dict | None = None) -> TradingStrategy | None:
        """Create is intentionally unused by the causal saved path."""
        if name != self._definition["name"]:
            return None
        parser = StrategyDefinitionParser()
        validation = parser.parse(self._definition, param_overrides=params or {})
        if validation.definition is None:
            return None
        return StrategyDefinitionFactory().create(validation.definition)

    def list_metadata(self) -> list[StrategyMeta]:
        """Return metadata for the saved definition."""
        return [
            StrategyMeta(
                name=self._definition["name"],
                variant=DataMode.REAL,
                kind=StrategyKind.USER_DEFINED,
                description="Saved VWAP strategy",
                required_indicators=["vwap"],
            )
        ]

    def exists(self, name: str) -> bool:
        """Return whether the saved definition exists."""
        return name == self._definition["name"]

    def definition_for(self, name: str) -> dict | None:
        """Return the saved JSON definition for causal enrichment."""
        if name != self._definition["name"]:
            return None
        return self._definition


def _saved_use_case(provider: SavedJsonStrategyProvider) -> RunBacktestUseCase:
    """Create the saved/named strategy backtest use case."""
    return RunBacktestUseCase(
        engine=BacktestRunner(),
        strategy_provider=provider,
        converter=PandasBarFrameConverter(),
        parser=StrategyDefinitionParser(),
        strategy_factory=StrategyDefinitionFactory(),
        enricher=_enricher(),
    )


class TestSavedStrategyCausalBacktest:
    """Black-box tests comparing saved and inline JSON backtests."""

    def test_saved_strategy_matches_inline_causal_backtest(self):
        """Saved default backtest uses the same causal enricher as inline JSON."""
        definition = _vwap_strategy()
        bars = _bars()
        inline = _inline_use_case().execute(
            BacktestStrategyDefinitionRequest(
                definition=definition,
                bars=bars,
                execution=ExecutionConfig(),
                symbol="TEST",
                interval="1h",
            )
        )
        saved = _saved_use_case(SavedJsonStrategyProvider(definition)).execute(
            BacktestRequest(
                bars=bars,
                strategy_name=definition["name"],
                execution=ExecutionConfig(),
                symbol="TEST",
                interval="1h",
            )
        )

        assert inline.valid is True, inline.errors
        assert inline.result is not None
        assert saved.error is None
        assert saved.enrichment_mode == "live_parity_streaming"
        assert saved.live_parity_safe is True
        assert saved.parity_warnings == []
        assert saved.trades == inline.result.trades
        assert saved.final_value == inline.result.final_value
        assert saved.total_trades == inline.result.total_trades
