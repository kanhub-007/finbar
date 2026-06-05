"""EnrichmentJobManager interface for asynchronous enrichment jobs."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from finbar.core.domain.entities.enrichment_job import EnrichmentJob


class EnrichmentJobManager(ABC):
    """Manage asynchronous enrichment jobs and paginated result artifacts."""

    @abstractmethod
    def start(
        self,
        params: dict[str, Any],
        runner: Callable[[EnrichmentJob], Awaitable[None]],
    ) -> EnrichmentJob:
        """Create and start a background enrichment job."""
        ...

    @abstractmethod
    def get(self, job_id: str) -> EnrichmentJob | None:
        """Return a job by ID."""
        ...

    @abstractmethod
    def update(self, job: EnrichmentJob, **updates: Any) -> None:
        """Update mutable job state."""
        ...

    @abstractmethod
    def store_result(self, job: EnrichmentJob, bars: list[dict]) -> None:
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
    def cancel(self, job_id: str) -> EnrichmentJob | None:
        """Cancel a queued or running job."""
        ...
