"""GetBacktestTradesResult — paginated stored trade DTO."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GetBacktestTradesResult:
    """Result containing one page of stored backtest trades."""

    found: bool
    """True when the result ID exists."""

    result_id: str
    """Requested result identifier."""

    page: int = 0
    """Returned zero-based page number."""

    page_size: int = 0
    """Page size after clamping."""

    total_pages: int = 0
    """Total trade pages."""

    total_trades: int = 0
    """Total trades available."""

    trade_count: int = 0
    """Number of trades returned."""

    trades: list[dict[str, Any]] = field(default_factory=list)
    """Paged trades."""

    error: str | None = None
    """Error message if lookup failed."""
