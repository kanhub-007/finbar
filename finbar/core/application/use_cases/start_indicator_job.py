"""StartIndicatorJobUseCase — submit asynchronous indicator computation."""

from finbar.core.application.dto.start_indicator_job_request import (
    StartIndicatorJobRequest,
)
from finbar.core.domain.entities.indicator_job import IndicatorJob
from finbar.core.domain.interfaces.indicator_job_manager import IndicatorJobManager
from finbar.core.domain.interfaces.indicator_job_runner import IndicatorJobRunner


class StartIndicatorJobUseCase:
    """Create and start an indicator computation job."""

    def __init__(
        self,
        manager: IndicatorJobManager,
        runner: IndicatorJobRunner,
    ):
        """Create the use case with injected manager and runner."""
        self._manager = manager
        self._runner = runner

    def execute(self, request: StartIndicatorJobRequest) -> IndicatorJob:
        """Submit the job and return its queued state."""
        return self._manager.start(_params(request), self._runner.run)


def _params(request: StartIndicatorJobRequest) -> dict:
    return {
        "symbol": request.symbol.upper(),
        "source": request.source,
        "interval": request.interval,
        "mode": request.mode,
        "indicators": list(request.indicators),
        "definition": request.definition,
        "params": dict(request.params),
        "timeframe_alias": request.timeframe_alias or "primary",
        "start_date": request.start_date,
        "end_date": request.end_date,
    }
