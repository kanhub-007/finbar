"""QueryCachedPricesUseCase — retrieve OHLCV bars from local cache.

Thin wrapper over PriceCacheRepository.query_bars().
"""

import logging

from finbar.core.application.dto.cached_prices_result import CachedPricesResult
from finbar.core.domain.entities.data_source import DataSource
from finbar.core.domain.entities.interval import Interval
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
        validation_error = _validate_query(source, interval)
        if validation_error:
            return CachedPricesResult(
                symbol=symbol,
                source=source,
                interval=interval,
                bars=[],
                bar_count=0,
                error=validation_error,
            )

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


def _validate_query(source: str, interval: str) -> str | None:
    """Validate cached query source and interval values."""
    try:
        DataSource(source)
    except ValueError:
        allowed = ", ".join(item.value for item in DataSource)
        return f"Unknown source '{source}'. Allowed: {allowed}"

    try:
        Interval(interval)
    except ValueError:
        allowed = ", ".join(item.value for item in Interval)
        return f"Unknown interval '{interval}'. Allowed: {allowed}"

    return None
