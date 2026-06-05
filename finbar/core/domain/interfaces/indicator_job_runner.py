"""IndicatorJobRunner interface for executing indicator jobs."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.indicator_job import IndicatorJob


class IndicatorJobRunner(ABC):
    """Execute asynchronous indicator job work."""

    @abstractmethod
    async def run(self, job: IndicatorJob) -> None:
        """Run the supplied indicator job."""
        ...
