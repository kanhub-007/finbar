"""OptimizationJobRunner interface for executing optimization jobs."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.optimization_job import OptimizationJob


class OptimizationJobRunner(ABC):
    """Execute asynchronous optimization work (grid search, etc.)."""

    @abstractmethod
    async def run(self, job: OptimizationJob) -> None:
        """Run the supplied optimization job."""
        ...
