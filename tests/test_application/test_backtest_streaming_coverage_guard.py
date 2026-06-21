"""Tests for guarding Finbar's causal default with streaming coverage.

Scenario 3 from all-metrics causal streaming parity: a strategy requiring a
STREAMING_UNSUPPORTED metric must not silently trade on the broken streaming
value when the default live_parity_streaming mode is requested.
"""

from __future__ import annotations

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
from finbar.infrastructure.services.strategy_definition_factory import (
    StrategyDefinitionFactory,
)


def _make_use_case() -> BacktestStrategyDefinitionUseCase:
    """Create the JSON-strategy backtest use case with raw-bar enrichment."""
    enricher = MultiTimeframeBarEnricher(
        indicator_calculator=PandasTaIndicatorCalculator(),
        bar_converter=PandasBarFrameConverter(),
        timeframe_merger=PandasTimeframeBarMerger(),
        feature_calculator=PandasStrategyFeatureCalculator(),
    )
    return BacktestStrategyDefinitionUseCase(
        engine=BacktestRunner(),
        converter=PandasBarFrameConverter(),
        strategy_factory=StrategyDefinitionFactory(),
        parser=StrategyDefinitionParser(),
        enricher=enricher,
    )


def _bars(count: int = 80) -> list[dict]:
    """Return deterministic raw OHLCV bars with timestamps."""
    return [
        {
            "timestamp": f"2026-01-{(i // 24) + 1:02d}T{i % 24:02d}:00:00Z",
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 1000.0 + (i * 10.0),
        }
        for i in range(count)
    ]


def _vwap_strategy() -> dict:
    """Return a valid strategy requiring the unsupported `vwap` metric."""
    return {
        "schema_version": "2.0",
        "name": "vwap_guard_strategy",
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


class TestBacktestStreamingCoverageGuard:
    """Black-box tests for unsupported-metric handling in causal mode."""

    def test_default_live_parity_does_not_silently_use_unsupported_metric(self):
        """Unsupported metrics fall back or fail loudly; never marked safe."""
        result = _make_use_case().execute(
            BacktestStrategyDefinitionRequest(
                definition=_vwap_strategy(),
                bars=_bars(),
                symbol="TEST",
                interval="1h",
            )
        )

        assert result.valid is True
        assert result.result is not None
        assert result.result.live_parity_safe is False
        assert result.result.enrichment_mode in {"batch_full_frame", "failed"}
        assert any(
            "vwap" in warning.lower()
            for warning in result.result.parity_warnings
        )
