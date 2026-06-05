"""OptimizationJobManager interface for parameter sweep jobs."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from finbar.core.domain.entities.optimization_job import OptimizationJob


class OptimizationJobManager(ABC):
    """Manage asynchronous optimization jobs."""

    @abstractmethod
    def start(
        self,
        params: dict[str, Any],
        runner: Callable[[OptimizationJob], Awaitable[None]],
    ) -> OptimizationJob:
        """Create and start a background optimization job."""
        ...

    @abstractmethod
    def get(self, job_id: str) -> OptimizationJob | None:
        """Return a job by ID."""
        ...

    @abstractmethod
    def update(self, job: OptimizationJob, **updates: Any) -> None:
        """Update mutable job state."""
        ...

    @abstractmethod
    def cancel(self, job_id: str) -> OptimizationJob | None:
        """Cancel a queued or running job."""
        ...
