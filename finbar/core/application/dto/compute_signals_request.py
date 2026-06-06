"""ComputeSignalsRequest — input DTO for signal interpretation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ComputeSignalsRequest:
    """Request to compute signal interpretation columns from enriched bars."""

    bars: list[dict]
    """Already-enriched OHLCV bars with indicator columns."""

    symbol: str = ""
    """Ticker symbol (for metadata)."""

    interval: str = ""
    """Bar interval (for metadata)."""
