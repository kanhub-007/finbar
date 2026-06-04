"""FetchPricesUseCase — fetch raw OHLCV from source, validate, cache, return.

Fetch → validate → save → return (no enrichment).

Depends on StockDataFetcher (Strategy) and PriceCacheRepository (Repository).
"""

import logging

from finbar.core.application.dto.fetch_prices_request import FetchPricesRequest
from finbar.core.application.dto.fetch_prices_result import FetchPricesResult
from finbar.core.domain.interfaces.price_cache_repository import (
    PriceCacheRepository,
)
from finbar.core.domain.interfaces.stock_data_fetcher import StockDataFetcher

logger = logging.getLogger(__name__)


class FetchPricesUseCase:
    """Fetch raw OHLCV bars from a data source, validate, cache, and return.

    Constructor injection: receives a fetcher and cache repository.
    The caller chooses the source by passing the appropriate fetcher.
    """

    def __init__(
        self,
        fetcher: StockDataFetcher,
        cache: PriceCacheRepository,
    ):
        self._fetcher = fetcher
        self._cache = cache

    def execute(self, request: FetchPricesRequest) -> FetchPricesResult:
        """Execute the fetch-and-store pipeline.

        Always fetches fresh from the source — this is the "fresh data"
        path. For cached queries, use QueryCachedPricesUseCase instead.

        Args:
            request: FetchPricesRequest with symbol, source, interval, date range.

        Returns:
            FetchPricesResult with bars, count, origin="fresh".
        """
        # 1. Fetch from source
        bars = self._fetcher.fetch(
            symbol=request.symbol,
            interval=request.interval,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        if not bars:
            return FetchPricesResult(
                symbol=request.symbol,
                source=request.source,
                interval=request.interval,
                bars=[],
                bar_count=0,
                origin="fresh",
                error="No data returned from source",
            )

        # 2. Save to cache (side effect)
        saved = self._cache.save_bars(bars)
        logger.info(
            "Fetched %d bars for %s (%s), saved %d to cache",
            len(bars),
            request.symbol,
            request.interval,
            saved,
        )

        return FetchPricesResult(
            symbol=request.symbol,
            source=request.source,
            interval=request.interval,
            bars=bars,
            bar_count=len(bars),
            origin="fresh",
        )
