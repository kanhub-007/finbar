"""GetLatestQuoteUseCase — fetch the most recent OHLCV bar.

Adapted from h_stocks/core/fetchers/yfinance_price_fetcher.py:fetch_latest_bar().
"""

import logging

from finbar.core.domain.entities.price_bar import PriceBar
from finbar.core.domain.interfaces.stock_data_fetcher import StockDataFetcher

logger = logging.getLogger(__name__)


class GetLatestQuoteUseCase:
    """Fetch the single most recent OHLCV bar for a symbol."""

    def __init__(self, fetcher: StockDataFetcher):
        self._fetcher = fetcher

    def execute(self, symbol: str) -> PriceBar | None:
        """Fetch the latest OHLCV bar.

        Args:
            symbol: Ticker symbol.

        Returns:
            Latest PriceBar or None if unavailable.
        """
        return self._fetcher.fetch_latest(symbol)
