"""Spec 2026-06-23 Scenario 5 — saved run_backtest uses the fully wired
live-parity use case (features included).

The saved/named strategy path previously built a partial
``BacktestStrategyDefinitionUseCase`` inline, omitting the feature
calculator (and data validator). A strategy that relies on a declared
``feature`` would then silently skip feature computation, so its result
diverged from a direct ``backtest_strategy_definition`` run. The fix is
DI: the startup composition root injects a fully wired delegate.

Classical school, black-box: real parsers/enrichers/feature calculators
and the real backtest runner on deterministic timestamped bars. We assert
that the saved path produces the same trades as the direct path and that
the declared feature actually drives the result.
"""

from __future__ import annotations

from finbar_strategy_runtime.domain.entities.strategy_kind import StrategyKind
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
    """Deterministic timestamped OHLCV bars with a rising-trend breakout."""
    return [
        {
            "timestamp": f"2026-02-{(i // 24) + 1:02d}T{i % 24:02d}:00:00Z",
            "open": 100.0 + i,
            "high": 101.5 + i,
            "low": 99.0 + i,
            "close": 101.0 + i,
            "volume": 1000.0 + (i * 10.0),
        }
        for i in range(count)
    ]


def _feature_strategy() -> dict:
    """A strategy whose entry depends on a declared rolling_max feature."""
    return {
        "schema_version": "2.0",
        "name": "saved_feature_breakout",
        "features": [
            {
                "name": "prior_high",
                "type": "rolling_max",
                "source": "high",
                "window": 3,
                "shift": 1,
            }
        ],
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {
                                "left": "close",
                                "operator": ">",
                                "right": "prior_high",
                            }
                        ]
                    }
                }
            }
        },
    }


def _enricher() -> MultiTimeframeBarEnricher:
    return MultiTimeframeBarEnricher(
        indicator_calculator=PandasTaIndicatorCalculator(),
        bar_converter=PandasBarFrameConverter(),
        timeframe_merger=PandasTimeframeBarMerger(),
        feature_calculator=PandasStrategyFeatureCalculator(),
    )


def _fully_wired_definition_use_case() -> BacktestStrategyDefinitionUseCase:
    """The delegate the startup composition root would build."""
    return BacktestStrategyDefinitionUseCase(
        engine=BacktestRunner(),
        converter=PandasBarFrameConverter(),
        strategy_factory=StrategyDefinitionFactory(),
        parser=StrategyDefinitionParser(),
        enricher=_enricher(),
        feature_calculator=PandasStrategyFeatureCalculator(),
    )


class SavedJsonStrategyProvider(StrategyProvider):
    """In-memory saved strategy provider."""

    def __init__(self, definition: dict):
        self._definition = definition

    def create(self, name: str, params: dict | None = None):
        if name != self._definition["name"]:
            return None
        validation = StrategyDefinitionParser().parse(
            self._definition, param_overrides=params or {}
        )
        if validation.definition is None:
            return None
        return StrategyDefinitionFactory().create(validation.definition)

    def list_metadata(self) -> list[StrategyMeta]:
        return [
            StrategyMeta(
                name=self._definition["name"],
                variant=DataMode.REAL,
                kind=StrategyKind.USER_DEFINED,
                description="Saved feature breakout",
                required_indicators=[],
            )
        ]

    def exists(self, name: str) -> bool:
        return name == self._definition["name"]

    def definition_for(self, name: str):
        if name != self._definition["name"]:
            return None
        return self._definition


class TestSavedStrategyFeatureWiring:
    """Saved run_backtest must compute declared features like the direct path."""

    def test_saved_path_matches_direct_path_when_feature_drives_entry(self):
        definition = _feature_strategy()
        bars = _bars()

        direct = _fully_wired_definition_use_case().execute(
            BacktestStrategyDefinitionRequest(
                definition=definition,
                bars=bars,
                execution=ExecutionConfig(),
                symbol="TEST",
                interval="1h",
            )
        )
        assert direct.valid is True, direct.errors
        assert direct.result is not None
        # Sanity: the feature genuinely drives at least one trade on this data.
        assert direct.result.total_trades >= 1, (
            "test fixture should produce a feature-driven trade"
        )

        saved = RunBacktestUseCase(
            engine=BacktestRunner(),
            strategy_provider=SavedJsonStrategyProvider(definition),
            converter=PandasBarFrameConverter(),
            parser=StrategyDefinitionParser(),
            strategy_factory=StrategyDefinitionFactory(),
            enricher=_enricher(),
            strategy_definition_backtester=_fully_wired_definition_use_case(),
        ).execute(
            BacktestRequest(
                bars=bars,
                strategy_name=definition["name"],
                execution=ExecutionConfig(),
                symbol="TEST",
                interval="1h",
            )
        )

        assert saved.error is None, saved.error
        assert saved.enrichment_mode == "live_parity_streaming"
        assert saved.total_trades == direct.result.total_trades
        assert saved.trades == direct.result.trades
        assert saved.final_value == direct.result.final_value
