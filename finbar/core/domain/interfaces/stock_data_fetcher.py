"""StockDataFetcher interface — contract for fetching OHLCV data from a source.

Every data source (yfinance, Hyperliquid, etc.) implements this interface.
The use case depends on this ABC, never on a concrete fetcher — Strategy pattern.

Public method shape designed from h_stocks/core/fetchers/yfinance_price_fetcher.py
(YFinanceFetcher class) and h_stocks/core/domain/orchestrator/stock.py
(fetch_and_store flow).
"""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.price_bar import PriceBar
from finbar.core.domain.entities.symbol_info import SymbolInfo


class StockDataFetcher(ABC):
    """Fetches OHLCV price bars and symbol metadata from a data source."""

    @abstractmethod
    def fetch(
        self,
        symbol: str,
        interval: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[PriceBar]:
        """Fetch raw OHLCV price bars for a symbol.

        Args:
            symbol: Ticker symbol (e.g., 'AAPL').
            interval: Time interval ('5min', '30min', '1h', '1d', '1w').
            start_date: Optional start date (ISO format, e.g. '2024-01-01').
            end_date: Optional end date (ISO format).

        Returns:
            List of PriceBar domain entities. Empty list if no data.
        """
        ...

    @abstractmethod
    def fetch_latest(self, symbol: str) -> PriceBar | None:
        """Fetch the single most recent OHLCV bar for a symbol.

        Args:
            symbol: Ticker symbol.

        Returns:
            Latest PriceBar or None if unavailable.
        """
        ...

    @abstractmethod
    def fetch_info(self, symbol: str) -> SymbolInfo | None:
        """Fetch company/asset metadata for a symbol.

        Args:
            symbol: Ticker symbol.

        Returns:
            SymbolInfo or None if unavailable.
        """
        ...
