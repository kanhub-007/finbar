"""Tests for Finbar JSON-strategy causal streaming integration.

Scenarios 3 and 11 from all-metrics causal streaming parity: default
``live_parity_streaming`` must be safe for fixed catalog metrics, and explicit
``batch_full_frame`` remains a labelled research opt-in.
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
    """Return a valid strategy requiring the formerly unsupported vwap metric."""
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


def _vp_poc_strategy() -> dict:
    """Return a valid strategy requiring frame-dependent session VP."""
    return {
        "schema_version": "2.0",
        "name": "vp_poc_research_strategy",
        "indicators": [{"name": "primary_vp_poc", "type": "vp_poc"}],
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {
                                "left": "close",
                                "operator": ">",
                                "right": "primary_vp_poc",
                            }
                        ]
                    }
                }
            }
        },
    }


class TestBacktestStreamingCoverageGuard:
    """Black-box tests for causal default and research batch opt-in."""

    def test_default_live_parity_uses_vwap_after_metric_is_fixed(self):
        """Formerly unsupported vwap now stays causal and live-parity safe."""
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
        assert result.result.live_parity_safe is True
        assert result.result.enrichment_mode == "live_parity_streaming"
        assert result.result.parity_warnings == []

    def test_explicit_batch_full_frame_is_labelled_research_opt_in(self):
        """Batch mode remains available but warns for frame-dependent metrics."""
        result = _make_use_case().execute(
            BacktestStrategyDefinitionRequest(
                definition=_vp_poc_strategy(),
                bars=_bars(),
                symbol="TEST",
                interval="1h",
                enrichment_mode="batch_full_frame",
            )
        )

        assert result.valid is True, result.errors
        assert result.result is not None
        assert result.result.enrichment_mode == "batch_full_frame"
        assert result.result.live_parity_safe is False
        assert any("vp_poc" in warning for warning in result.result.parity_warnings)
