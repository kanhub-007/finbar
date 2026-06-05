"""StartEnrichmentJobUseCase — submit asynchronous enrichment work."""

from finbar.core.application.dto.start_enrichment_job_request import (
    StartEnrichmentJobRequest,
)
from finbar.core.domain.entities.enrichment_job import EnrichmentJob
from finbar.core.domain.interfaces.enrichment_job_manager import EnrichmentJobManager
from finbar.core.domain.interfaces.enrichment_job_runner import EnrichmentJobRunner


class StartEnrichmentJobUseCase:
    """Create and start an enrichment background job."""

    def __init__(
        self,
        manager: EnrichmentJobManager,
        runner: EnrichmentJobRunner,
    ):
        """Create the use case with injected manager and runner."""
        self._manager = manager
        self._runner = runner

    def execute(self, request: StartEnrichmentJobRequest) -> EnrichmentJob:
        """Submit the job and return its queued state."""
        return self._manager.start(_params(request), self._runner.run)


def _params(request: StartEnrichmentJobRequest) -> dict:
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
