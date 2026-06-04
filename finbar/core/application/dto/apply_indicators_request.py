"""ApplyIndicatorsRequest DTO — input for the apply indicators use case."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ApplyIndicatorsRequest:
    """Request to apply technical indicators to OHLCV bars.

    bars: list of dicts with keys open, high, low, close, volume.
    indicators: list of indicator names to compute (e.g. "rsi_14", "sma_20").
    """

    bars: list[dict]
    """Raw OHLCV bars. Each dict must have keys: open, high, low, close, volume."""

    indicators: list[str] = field(default_factory=list)
    """Indicator names to apply. Supports real (rsi_14, sma_20, macd, atr, etc.)
    and proxy (proxy_ibs, proxy_parkinson, etc.) indicators."""
