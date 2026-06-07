"""ListBacktestResultsResult — compact stored backtest records."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ListBacktestResultsResult:
    """Result containing stored backtest metadata records."""

    results: list[dict[str, Any]] = field(default_factory=list)
    """Stored result metadata records."""

    error: str | None = None
    """Error message if listing failed."""
