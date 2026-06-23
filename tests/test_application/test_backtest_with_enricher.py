"""Tests for BacktestStrategyDefinitionUseCase with the enricher wired in.

Scenario S2: Finbar's backtest delegates to the enricher (behaviour-preserving).
"""



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

# Reuse the strategy and bars from the existing SDK tests
from tests.test_application.test_strategy_json_sdk import (
    _bars_with_sma,
    _sma_strategy,
)


def _make_use_case_with_enricher() -> BacktestStrategyDefinitionUseCase:
    """Create the use case with an enricher wired in."""
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


def _make_legacy_use_case() -> BacktestStrategyDefinitionUseCase:
    """Create the use case without enricher (legacy path)."""
    return BacktestStrategyDefinitionUseCase(
        engine=BacktestRunner(),
        converter=PandasBarFrameConverter(),
        strategy_factory=StrategyDefinitionFactory(),
        parser=StrategyDefinitionParser(),
    )


class TestBacktestWithEnricher:
    """Black-box tests for the backtest use case with enricher wired in."""

    def test_enricher_path_produces_valid_backtest(self):
        """The enricher path produces a valid backtest with trades."""
        use_case = _make_use_case_with_enricher()
        bars = _bars_with_sma()

        result = use_case.execute(
            BacktestStrategyDefinitionRequest(
                definition=_sma_strategy(),
                bars=bars,
                symbol="TEST",
                interval="1d",
                initial_cash=10_000.0,
                risk_per_trade=0.10,
            )
        )

        assert result.valid is True, f"Errors: {result.errors}"
        assert result.result is not None
        assert not result.result.error
        assert len(result.result.trades) > 0

    def test_enricher_path_same_as_legacy_path(self):
        """Enricher path produces the same backtest result as legacy path."""
        bars = _bars_with_sma()
        strategy = _sma_strategy()

        req = BacktestStrategyDefinitionRequest(
            definition=strategy,
            bars=bars,
            symbol="TEST",
            interval="1d",
            initial_cash=10_000.0,
            risk_per_trade=0.10,
        )

        legacy_result = _make_legacy_use_case().execute(req)
        assert legacy_result.valid, f"Legacy errors: {legacy_result.errors}"

        enricher_result = _make_use_case_with_enricher().execute(req)
        assert enricher_result.valid, f"Enricher errors: {enricher_result.errors}"

        assert len(legacy_result.result.trades) == len(
            enricher_result.result.trades
        )
        assert (
            legacy_result.result.final_value
            == enricher_result.result.final_value
        )
