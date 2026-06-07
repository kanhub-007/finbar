"""StartOptimizationJobUseCase — submit grid search optimization work."""

from finbar.core.application.dto.start_optimization_job_request import (
    StartOptimizationJobRequest,
)
from finbar.core.domain.entities.optimization_job import OptimizationJob
from finbar.core.domain.interfaces.optimization_job_manager import (
    OptimizationJobManager,
)
from finbar.core.domain.interfaces.optimization_job_runner import (
    OptimizationJobRunner,
)


class StartOptimizationJobUseCase:
    """Create and start an optimization background job."""

    def __init__(
        self,
        manager: OptimizationJobManager,
        runner: OptimizationJobRunner,
    ):
        """Create the use case with injected manager and runner."""
        self._manager = manager
        self._runner = runner

    def execute(self, request: StartOptimizationJobRequest) -> OptimizationJob:
        """Submit the job and return its queued state."""
        return self._manager.start(_params(request), self._runner.run)


def _params(request: StartOptimizationJobRequest) -> dict:
    return {
        "definition": request.definition,
        "bars_artifact_id": request.bars_artifact_id,
        "param_ranges": dict(request.param_ranges),
        "metric": request.metric,
        "search_method": request.search_method,
        "random_count": request.random_count,
        "informative_bars_artifact_ids": dict(request.informative_bars_artifact_ids),
        "initial_cash": request.initial_cash,
        "interval": request.interval,
        "risk_per_trade": request.risk_per_trade,
        "leverage": request.leverage,
        "risk_mode": request.risk_mode,
        "commission_pct": request.commission_pct,
        "slippage_pct": request.slippage_pct,
        "cap_explicit_size": request.cap_explicit_size,
        "reject_oversized_explicit_orders": (request.reject_oversized_explicit_orders),
        "allow_negative_cash": request.allow_negative_cash,
        "market_calendar": request.market_calendar,
    }
