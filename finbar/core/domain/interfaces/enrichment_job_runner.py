"""EnrichmentJobRunner interface for executing enrichment jobs."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.enrichment_job import EnrichmentJob


class EnrichmentJobRunner(ABC):
    """Execute asynchronous enrichment job work."""

    @abstractmethod
    async def run(self, job: EnrichmentJob) -> None:
        """Run the supplied enrichment job."""
        ...
