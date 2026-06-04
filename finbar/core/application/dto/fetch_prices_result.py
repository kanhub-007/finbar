"""FetchPricesResult DTO — output from the fetch prices use case."""

from dataclasses import dataclass

from finbar.core.domain.entities.price_bar import PriceBar


@dataclass(frozen=True)
class FetchPricesResult:
    """Result of a fetch operation — fresh or cached bars with metadata."""

    symbol: str
    source: str
    interval: str
    bars: list[PriceBar]
    bar_count: int
    origin: str  # "fresh" or "cache"
    error: str | None = None
