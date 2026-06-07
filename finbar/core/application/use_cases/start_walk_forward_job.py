"""StartWalkForwardJobUseCase — submit walk-forward optimization work."""

from finbar.core.application.dto.start_walk_forward_job_request import (
    StartWalkForwardJobRequest,
)
from finbar.core.domain.entities.optimization_job import OptimizationJob
from finbar.core.domain.interfaces.optimization_job_manager import (
    OptimizationJobManager,
)
from finbar.core.domain.interfaces.optimization_job_runner import (
    OptimizationJobRunner,
)


class StartWalkForwardJobUseCase:
    """Create and start a walk-forward optimization background job."""

    def __init__(
        self,
        manager: OptimizationJobManager,
        runner: OptimizationJobRunner,
    ):
        """Create the use case with injected manager and runner.

        The runner should be a WalkForwardOptimizer instance.
        """
        self._manager = manager
        self._runner = runner

    def execute(self, request: StartWalkForwardJobRequest) -> OptimizationJob:
        """Submit the job and return its queued state."""
        return self._manager.start(_build_params(request), self._runner.run)


def _build_params(request: StartWalkForwardJobRequest) -> dict:
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
        "leverage": request.execution.leverage_multiplier,
        "risk_mode": request.execution.risk_mode,
        "commission_pct": request.execution.commission_pct,
        "slippage_pct": request.execution.slippage_pct,
        "cap_explicit_size": request.execution.cap_explicit_size,
        "reject_oversized_explicit_orders": (
            request.execution.reject_oversized_explicit_orders
        ),
        "allow_negative_cash": request.execution.allow_negative_cash,
        "market_calendar": request.execution.market_calendar,
        "borrow_fee_annual_pct": request.execution.borrow_fee_annual_pct,
        "margin_mode": request.execution.margin_mode,
        "maintenance_margin_pct": request.execution.maintenance_margin_pct,
        "enable_funding": request.execution.enable_funding,
        "funding_rate": request.execution.funding_rate,
        "wf_folds": request.wf_folds,
        "wf_train_ratio": request.wf_train_ratio,
        "wf_anchor": request.wf_anchor,
        "wf_min_train_bars": request.wf_min_train_bars,
        "wf_min_test_bars": request.wf_min_test_bars,
    }
