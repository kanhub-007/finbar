"""QueryArtifactBarsResult — paginated artifact bar query result DTO."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QueryArtifactBarsResult:
    """Result containing one page of artifact bars."""

    found: bool
    """True when the artifact exists."""

    artifact_id: str
    """Artifact identifier queried."""

    page: int = 0
    """Returned zero-based page number."""

    page_size: int = 0
    """Requested page size after clamping."""

    total_pages: int = 0
    """Total pages available for the filtered query."""

    total_bar_count: int = 0
    """Total bars available after filtering."""

    bar_count: int = 0
    """Number of bars returned in this page."""

    columns: list[str] = field(default_factory=list)
    """Columns returned in each bar."""

    bars: list[dict] = field(default_factory=list)
    """Paged artifact bars."""

    error: str | None = None
    """Error message if query failed."""
