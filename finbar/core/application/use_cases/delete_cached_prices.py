"""DeleteCachedPricesUseCase — remove OHLCV bars from the local cache.

Thin wrapper over PriceCacheRepository.delete_bars().
Symbol is required; other params narrow the deletion scope.
"""

import logging

from finbar.core.domain.interfaces.price_cache_repository import (
    PriceCacheRepository,
)

logger = logging.getLogger(__name__)


class DeleteCachedPricesUseCase:
    """Delete cached OHLCV bars for a symbol, optionally scoped by
    source, interval, and date."""

    def __init__(self, cache: PriceCacheRepository):
        self._cache = cache

    def execute(
        self,
        symbol: str,
        source: str | None = None,
        interval: str | None = None,
        before_date: str | None = None,
    ) -> int:
        """Delete cached bars.

        Args:
            symbol: Ticker symbol (required).
            source: Optional source filter.
            interval: Optional interval filter.
            before_date: Optional — delete bars before this date.

        Returns:
            Number of bars deleted.
        """
        deleted = self._cache.delete_bars(
            symbol=symbol,
            source=source,
            interval=interval,
            before_date=before_date,
        )
        logger.info(
            "Deleted %d cached bars for %s (source=%s, interval=%s)",
            deleted,
            symbol,
            source or "*",
            interval or "*",
        )
        return deleted
