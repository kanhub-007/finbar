"""IndicatorJobManager interface for asynchronous indicator jobs."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from finbar.core.domain.entities.indicator_job import IndicatorJob


class IndicatorJobManager(ABC):
    """Manage asynchronous indicator jobs and paginated result artifacts."""

    @abstractmethod
    def start(
        self,
        params: dict[str, Any],
        runner: Callable[[IndicatorJob], Awaitable[None]],
    ) -> IndicatorJob:
        """Create and start a background indicator job."""
        ...

    @abstractmethod
    def get(self, job_id: str) -> IndicatorJob | None:
        """Return a job by ID."""
        ...

    @abstractmethod
    def update(self, job: IndicatorJob, **updates: Any) -> None:
        """Update mutable job state."""
        ...

    @abstractmethod
    def store_result(self, job: IndicatorJob, bars: list[dict]) -> None:
        """Store enriched bars for a completed job."""
        ...

    @abstractmethod
    def get_result_page(
        self,
        job_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int, int, int]:
        """Return bars plus page metadata: bars, page, page_size, total_pages."""
        ...

    @abstractmethod
    def cancel(self, job_id: str) -> IndicatorJob | None:
        """Cancel a queued or running job."""
        ...
