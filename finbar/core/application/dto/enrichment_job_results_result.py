"""Result DTO for paginated enrichment job results."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EnrichmentJobResultsResult:
    """Paginated enriched bars from a completed enrichment job."""

    found: bool
    """True when the job exists."""

    job_id: str = ""
    status: str = ""
    page: int = 0
    page_size: int = 500
    total_pages: int = 0
    total_bar_count: int = 0
    bar_count: int = 0
    bars: list[dict] = field(default_factory=list)
    error: str | None = None
