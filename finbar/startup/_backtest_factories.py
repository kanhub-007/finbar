"""Backtest infrastructure factories — runner, result store, backtest use cases."""

from sqlalchemy.orm import Session

from finbar.core.application.use_cases.apply_strategy_features import (
    ApplyStrategyFeaturesUseCase,
)
from finbar.core.application.use_cases.backtest_strategy_definition import (
    BacktestStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.get_backtest_equity import (
    GetBacktestEquityUseCase,
)
from finbar.core.application.use_cases.get_backtest_summary import (
    GetBacktestSummaryUseCase,
)
from finbar.core.application.use_cases.get_backtest_trades import (
    GetBacktestTradesUseCase,
)
from finbar.core.application.use_cases.list_backtest_results import (
    ListBacktestResultsUseCase,
)
from finbar.core.application.use_cases.run_backtest import RunBacktestUseCase
from finbar.core.application.use_cases.run_portfolio_backtest import (
    RunPortfolioBacktestUseCase,
)
from finbar.core.application.use_cases.store_backtest_result import (
    StoreBacktestResultUseCase,
)
from finbar.infrastructure.data.connection import SessionLocal
from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.in_memory_backtest_result_store import (
    InMemoryBacktestResultStore,
)

_bt_runner: BacktestRunner | None = None
_backtest_result_store: InMemoryBacktestResultStore | None = None


def get_backtest_runner() -> BacktestRunner:
    """Return the shared backtest runner instance."""
    global _bt_runner
    if _bt_runner is None:
        _bt_runner = BacktestRunner()
    return _bt_runner


def get_backtest_result_store() -> InMemoryBacktestResultStore:
    """Return the shared server-side backtest result store."""
    global _backtest_result_store
    if _backtest_result_store is None:
        _backtest_result_store = InMemoryBacktestResultStore(
            session_factory=SessionLocal,
        )
    return _backtest_result_store


def make_store_backtest_result_use_case() -> StoreBacktestResultUseCase:
    """Create a use case for storing compact-access backtest results."""
    return StoreBacktestResultUseCase(get_backtest_result_store())


def make_list_backtest_results_use_case() -> ListBacktestResultsUseCase:
    """Create a use case for listing stored backtest results."""
    return ListBacktestResultsUseCase(get_backtest_result_store())


def make_get_backtest_summary_use_case() -> GetBacktestSummaryUseCase:
    """Create a use case for retrieving stored backtest summaries."""
    return GetBacktestSummaryUseCase(get_backtest_result_store())


def make_get_backtest_trades_use_case() -> GetBacktestTradesUseCase:
    """Create a use case for retrieving stored backtest trades."""
    return GetBacktestTradesUseCase(get_backtest_result_store())


def make_get_backtest_equity_use_case() -> GetBacktestEquityUseCase:
    """Create a use case for retrieving stored backtest equity."""
    return GetBacktestEquityUseCase(get_backtest_result_store())


def make_run_backtest_use_case(
    db: Session | None = None,
) -> RunBacktestUseCase:
    """Create a RunBacktestUseCase with built-in and optional DB strategies."""
    from finbar_strategy_runtime.indicators.multi_timeframe_bar_enricher import (
        MultiTimeframeBarEnricher,
    )

    from finbar.startup._indicator_factories import (
        get_bar_frame_converter,
        get_indicator_calculator,
        get_strategy_feature_calculator,
        get_timeframe_bar_merger,
    )
    from finbar.startup._strategy_factories import (
        get_json_strategy_factory,
        get_parser,
        make_strategy_provider,
    )

    enricher = MultiTimeframeBarEnricher(
        indicator_calculator=get_indicator_calculator(),
        bar_converter=get_bar_frame_converter(),
        timeframe_merger=get_timeframe_bar_merger(),
        feature_calculator=get_strategy_feature_calculator(),
    )
    return RunBacktestUseCase(
        get_backtest_runner(),
        make_strategy_provider(db),
        get_bar_frame_converter(),
        parser=get_parser(),
        strategy_factory=get_json_strategy_factory(),
        enricher=enricher,
    )


def make_run_portfolio_backtest_use_case(
    db: Session | None = None,
) -> RunPortfolioBacktestUseCase:
    """Create a RunPortfolioBacktestUseCase."""
    from finbar.startup._indicator_factories import get_bar_frame_converter
    from finbar.startup._strategy_factories import make_strategy_provider

    return RunPortfolioBacktestUseCase(
        make_strategy_provider(db),
        get_backtest_runner(),
        get_bar_frame_converter(),
    )


def make_backtest_strategy_definition_use_case() -> BacktestStrategyDefinitionUseCase:
    """Create a use case for unsaved JSON strategy backtests.

    Wires the enricher so raw OHLCV bars can be passed directly — the
    enricher handles indicator computation, MTF merge, and features inline.
    Pre-enriched bars (from async indicator jobs) still work via the
    legacy prepare_frame path.
    """
    from finbar_strategy_runtime.indicators.multi_timeframe_bar_enricher import (
        MultiTimeframeBarEnricher,
    )
    from finbar_strategy_runtime.indicators.required_data_validator import (
        RequiredDataValidator,
    )

    from finbar.startup._indicator_factories import (
        get_bar_frame_converter,
        get_indicator_calculator,
        get_strategy_feature_calculator,
        get_timeframe_bar_merger,
    )
    from finbar.startup._indicator_job_factories import get_indicator_job_manager
    from finbar.startup._strategy_factories import (
        get_json_strategy_factory,
        get_parser,
    )

    enricher = MultiTimeframeBarEnricher(
        indicator_calculator=get_indicator_calculator(),
        bar_converter=get_bar_frame_converter(),
        timeframe_merger=get_timeframe_bar_merger(),
        feature_calculator=get_strategy_feature_calculator(),
    )

    return BacktestStrategyDefinitionUseCase(
        get_backtest_runner(),
        get_bar_frame_converter(),
        get_json_strategy_factory(),
        parser=get_parser(),
        timeframe_merger=get_timeframe_bar_merger(),
        artifact_provider=get_indicator_job_manager(),
        feature_calculator=get_strategy_feature_calculator(),
        enricher=enricher,
        data_validator=RequiredDataValidator(),
    )


def make_apply_strategy_features_use_case() -> ApplyStrategyFeaturesUseCase:
    """Create a use case for applying strategy feature declarations."""
    from finbar.startup._indicator_factories import (
        get_bar_frame_converter,
        get_strategy_feature_calculator,
    )
    from finbar.startup._strategy_factories import get_parser

    return ApplyStrategyFeaturesUseCase(
        get_bar_frame_converter(),
        get_strategy_feature_calculator(),
        parser=get_parser(),
    )
