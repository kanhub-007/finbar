"""GetBacktestSummaryResult — compact backtest summary DTO."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GetBacktestSummaryResult:
    """Result containing a compact or full backtest response envelope."""

    found: bool
    """True when the result ID exists."""

    result_id: str
    """Requested result identifier."""

    response: dict[str, Any] = field(default_factory=dict)
    """Backtest response envelope."""

    error: str | None = None
    """Error message if lookup failed."""
