"""FetchDerivativesResult — output DTO for derivatives metrics fetch."""

from dataclasses import dataclass, field

from finbar.core.domain.entities.derivatives_metrics import DerivativesMetrics


@dataclass(frozen=True)
class FetchDerivativesResult:
    """Output from a derivatives metrics fetch operation."""

    symbol: str = ""
    """Ticker symbol."""

    interval: str = ""
    """Bar interval."""

    metrics: list[DerivativesMetrics] = field(default_factory=list)
    """Fetched derivatives metrics."""

    count: int = 0
    """Number of data points returned."""

    error: str | None = None
    """Error message if the fetch failed."""
