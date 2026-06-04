"""QueryCachedPricesUseCase — retrieve OHLCV bars from local cache.

Thin wrapper over PriceCacheRepository.query_bars().
"""

import logging

from finbar.core.application.dto.cached_prices_result import CachedPricesResult
from finbar.core.domain.interfaces.price_cache_repository import (
    PriceCacheRepository,
)

logger = logging.getLogger(__name__)


class QueryCachedPricesUseCase:
    """Query the local SQLite cache for previously-fetched OHLCV bars."""

    def __init__(self, cache: PriceCacheRepository):
        self._cache = cache

    def execute(
        self,
        symbol: str,
        source: str,
        interval: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> CachedPricesResult:
        """Retrieve cached bars for a symbol/source/interval/date range.

        Args:
            symbol: Ticker symbol.
            source: Data source.
            interval: Time interval.
            start_date: Optional start filter (ISO format).
            end_date: Optional end filter (ISO format).

        Returns:
            CachedPricesResult with bars and count.
        """
        bars = self._cache.query_bars(
            symbol=symbol,
            source=source,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
        )

        return CachedPricesResult(
            symbol=symbol,
            source=source,
            interval=interval,
            bars=bars,
            bar_count=len(bars),
        )
