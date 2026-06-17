"""Indicator/artifact job factories — job managers, runners, artifact access."""

from finbar.core.application.use_cases.cancel_indicator_job import (
    CancelIndicatorJobUseCase,
)
from finbar.core.application.use_cases.compute_strategy_indicators import (
    ComputeStrategyIndicatorsUseCase,
)
from finbar.core.application.use_cases.delete_artifact import DeleteArtifactUseCase
from finbar.core.application.use_cases.describe_artifact import DescribeArtifactUseCase
from finbar.core.application.use_cases.get_indicator_job_progress import (
    GetIndicatorJobProgressUseCase,
)
from finbar.core.application.use_cases.get_indicator_job_results import (
    GetIndicatorJobResultsUseCase,
)
from finbar.core.application.use_cases.list_artifacts import ListArtifactsUseCase
from finbar.core.application.use_cases.query_artifact_bars import (
    QueryArtifactBarsUseCase,
)
from finbar.core.application.use_cases.run_strategy_pipeline import (
    RunStrategyPipelineUseCase,
)
from finbar.core.application.use_cases.start_indicator_job import (
    StartIndicatorJobUseCase,
)
from finbar.infrastructure.data.connection import SessionLocal
from finbar.infrastructure.repositories.sql_price_cache_repository import (
    SqlPriceCacheRepository,
)
from finbar.infrastructure.services.in_memory_indicator_job_manager import (
    InMemoryIndicatorJobManager,
)
from finbar.infrastructure.services.indicator_job_runner import (
    CachedPriceIndicatorJobRunner,
)

_indicator_job_manager: InMemoryIndicatorJobManager | None = None
_indicator_job_runner: CachedPriceIndicatorJobRunner | None = None


def get_indicator_job_manager() -> InMemoryIndicatorJobManager:
    """Lazy-init the indicator job manager."""
    global _indicator_job_manager
    if _indicator_job_manager is None:
        _indicator_job_manager = InMemoryIndicatorJobManager(
            session_factory=SessionLocal,
        )
    return _indicator_job_manager


def get_indicator_job_runner() -> CachedPriceIndicatorJobRunner:
    """Return the shared indicator job runner."""
    global _indicator_job_runner
    if _indicator_job_runner is None:
        from finbar.startup._indicator_factories import (
            get_bar_frame_converter,
            get_indicator_calculator,
            get_strategy_feature_calculator,
        )
        from finbar.startup._strategy_factories import get_parser

        _indicator_job_runner = CachedPriceIndicatorJobRunner(
            session_factory=SessionLocal,
            manager=get_indicator_job_manager(),
            indicator_calculator=get_indicator_calculator(),
            converter=get_bar_frame_converter(),
            feature_calculator=get_strategy_feature_calculator(),
            parser=get_parser(),
        )
    return _indicator_job_runner


def make_start_indicator_job_use_case() -> StartIndicatorJobUseCase:
    """Create a use case for starting indicator jobs."""
    return StartIndicatorJobUseCase(
        get_indicator_job_manager(),
        get_indicator_job_runner(),
    )


def make_get_indicator_job_progress_use_case() -> GetIndicatorJobProgressUseCase:
    """Create a use case for indicator job progress."""
    return GetIndicatorJobProgressUseCase(get_indicator_job_manager())


def make_get_indicator_job_results_use_case() -> GetIndicatorJobResultsUseCase:
    """Create a use case for paginated indicator job results."""
    return GetIndicatorJobResultsUseCase(get_indicator_job_manager())


def make_cancel_indicator_job_use_case() -> CancelIndicatorJobUseCase:
    """Create a use case for cancelling indicator jobs."""
    return CancelIndicatorJobUseCase(get_indicator_job_manager())


def make_list_artifacts_use_case() -> ListArtifactsUseCase:
    """Create a use case for artifact discovery."""
    return ListArtifactsUseCase(get_indicator_job_manager())


def make_describe_artifact_use_case() -> DescribeArtifactUseCase:
    """Create a use case for artifact metadata inspection."""
    return DescribeArtifactUseCase(get_indicator_job_manager())


def make_query_artifact_bars_use_case() -> QueryArtifactBarsUseCase:
    """Create a use case for paginated artifact bar queries."""
    return QueryArtifactBarsUseCase(get_indicator_job_manager())


def make_delete_artifact_use_case() -> DeleteArtifactUseCase:
    """Create a use case for explicit artifact deletion."""
    return DeleteArtifactUseCase(get_indicator_job_manager())


def make_compute_strategy_indicators_use_case() -> ComputeStrategyIndicatorsUseCase:
    """Create a use case for computing indicators from a strategy definition."""
    from finbar.startup._strategy_factories import get_parser

    return ComputeStrategyIndicatorsUseCase(
        get_parser(),
        get_indicator_job_manager(),
        get_indicator_job_runner(),
    )


def make_run_strategy_pipeline_use_case() -> RunStrategyPipelineUseCase:
    """Create a use case for the one-call validate→compute→backtest pipeline."""
    from finbar.startup._backtest_factories import (
        get_backtest_result_store,
        make_backtest_strategy_definition_use_case,
    )
    from finbar.startup._strategy_factories import get_parser

    return RunStrategyPipelineUseCase(
        parser=get_parser(),
        manager=get_indicator_job_manager(),
        runner=get_indicator_job_runner(),
        backtest_use_case=make_backtest_strategy_definition_use_case(),
        store=get_backtest_result_store(),
        price_cache_factory=lambda: SqlPriceCacheRepository(SessionLocal()),
    )
