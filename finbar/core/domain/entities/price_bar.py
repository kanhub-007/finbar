"""PriceBar domain entity — a single OHLCV bar.

Shape inferred from the bar dict produced by
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PriceBar:
    """A single OHLCV price bar for one symbol at one timestamp.

    Immutable value object. Source and interval are embedded so each
    bar is self-describing.
    """

    symbol: str
    source: str
    interval: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None
