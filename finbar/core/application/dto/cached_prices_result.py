"""CachedPricesResult DTO — output from the cached query use case."""

from dataclasses import dataclass

from finbar.core.domain.entities.price_bar import PriceBar


@dataclass(frozen=True)
class CachedPricesResult:
    """Result of a cached query — bars found in local SQLite store."""

    symbol: str
    source: str
    interval: str
    bars: list[PriceBar]
    bar_count: int
    cached_at: str = ""
    error: str | None = None
