"""GetBacktestEquityResult — paginated/downsampled equity DTO."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GetBacktestEquityResult:
    """Result containing selected stored equity points."""

    found: bool
    """True when the result ID exists."""

    result_id: str
    """Requested result identifier."""

    mode: str = "daily"
    """Equity access mode."""

    page: int = 0
    """Returned zero-based page number."""

    page_size: int = 0
    """Page size after clamping."""

    total_pages: int = 0
    """Total pages for selected equity points."""

    total_equity_points: int = 0
    """Total selected equity points available."""

    equity_count: int = 0
    """Number of equity points returned."""

    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    """Selected equity points."""

    error: str | None = None
    """Error message if lookup failed."""
