"""StoreBacktestResultResult — compact response for stored backtests."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StoreBacktestResultResult:
    """Result returned after storing a full backtest result server-side."""

    result_id: str
    """Server-side backtest result identifier."""

    response: dict[str, Any] = field(default_factory=dict)
    """Compact response envelope for the stored result."""

    error: str | None = None
    """Error message if storing failed."""
