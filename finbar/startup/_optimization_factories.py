"""Optimization factories — grid search, walk-forward, optimization jobs."""

from finbar.core.application.use_cases.cancel_optimization_job import (
    CancelOptimizationJobUseCase,
)
from finbar.core.application.use_cases.get_optimization_job_progress import (
    GetOptimizationJobProgressUseCase,
)
from finbar.core.application.use_cases.get_optimization_job_results import (
    GetOptimizationJobResultsUseCase,
)
from finbar.core.application.use_cases.start_optimization_job import (
    StartOptimizationJobUseCase,
)
from finbar.core.application.use_cases.start_walk_forward_job import (
    StartWalkForwardJobUseCase,
)
from finbar.core.domain.entities.optimizer_config import OptimizerConfig
from finbar.infrastructure.services.grid_search_optimizer import (
    GridSearchOptimizer,
)
from finbar.infrastructure.services.in_memory_optimization_job_manager import (
    InMemoryOptimizationJobManager,
)
from finbar.infrastructure.services.walk_forward_optimizer import (
    WalkForwardOptimizer,
)

_optimization_job_manager: InMemoryOptimizationJobManager | None = None
_optimizer: GridSearchOptimizer | None = None
_walk_forward_optimizer: WalkForwardOptimizer | None = None


def get_optimization_job_manager() -> InMemoryOptimizationJobManager:
    """Lazy-init the optimization job manager."""
    global _optimization_job_manager
    if _optimization_job_manager is None:
        _optimization_job_manager = InMemoryOptimizationJobManager()
    return _optimization_job_manager


def _build_optimizer_config() -> OptimizerConfig:
    """Build the shared OptimizerConfig (used by grid-search and walk-forward)."""
    from finbar.startup._backtest_factories import get_backtest_runner
    from finbar.startup._indicator_factories import (
        get_bar_frame_converter,
        get_strategy_feature_calculator,
        get_timeframe_bar_merger,
    )
    from finbar.startup._indicator_job_factories import get_indicator_job_manager
    from finbar.startup._strategy_factories import get_json_strategy_factory, get_parser

    return OptimizerConfig(
        parser=get_parser(),
        engine=get_backtest_runner(),
        converter=get_bar_frame_converter(),
        strategy_factory=get_json_strategy_factory(),
        manager=get_optimization_job_manager(),
        artifact_provider=get_indicator_job_manager(),
        timeframe_merger=get_timeframe_bar_merger(),
        feature_calculator=get_strategy_feature_calculator(),
    )


def get_optimizer() -> GridSearchOptimizer:
    """Return the shared grid search optimizer."""
    global _optimizer
    if _optimizer is None:
        _optimizer = GridSearchOptimizer(_build_optimizer_config())
    return _optimizer


def get_walk_forward_optimizer() -> WalkForwardOptimizer:
    """Return the shared walk-forward optimizer."""
    global _walk_forward_optimizer
    if _walk_forward_optimizer is None:
        _walk_forward_optimizer = WalkForwardOptimizer(_build_optimizer_config())
    return _walk_forward_optimizer


def make_start_optimization_job_use_case() -> StartOptimizationJobUseCase:
    """Create a use case for starting optimization jobs."""
    return StartOptimizationJobUseCase(
        get_optimization_job_manager(),
        get_optimizer(),
    )


def make_start_walk_forward_job_use_case() -> StartWalkForwardJobUseCase:
    """Create a use case for starting walk-forward optimization jobs."""
    return StartWalkForwardJobUseCase(
        get_optimization_job_manager(),
        get_walk_forward_optimizer(),
    )


def make_get_optimization_job_progress_use_case() -> GetOptimizationJobProgressUseCase:
    """Create a use case for optimization job progress."""
    return GetOptimizationJobProgressUseCase(get_optimization_job_manager())


def make_get_optimization_job_results_use_case() -> GetOptimizationJobResultsUseCase:
    """Create a use case for optimization job results."""
    return GetOptimizationJobResultsUseCase(get_optimization_job_manager())


def make_cancel_optimization_job_use_case() -> CancelOptimizationJobUseCase:
    """Create a use case for cancelling optimization jobs."""
    return CancelOptimizationJobUseCase(get_optimization_job_manager())
