"""FetchDerivativesRequest — input DTO for fetching derivatives metrics."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FetchDerivativesRequest:
    """Input for fetching derivatives market metrics."""

    symbol: str
    """Ticker symbol (crypto only — e.g. BTC, ETH)."""

    interval: str = "1h"
    """Bar interval (e.g. 1h, 4h, 1d)."""

    start_time: str | None = None
    """ISO‑8601 start of the time range (inclusive)."""

    end_time: str | None = None
    """ISO‑8601 end of the time range (exclusive)."""
