"""PriceCacheRepository interface — contract for persisting and querying
OHLCV bars.

Repository pattern: all database access goes through this interface.
Use cases depend on this ABC, never on a concrete SQLite/Postgres
implementation.

Method shape adapted from h_stocks/core/domain/repositories.py:PriceRepository.
"""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.price_bar import PriceBar


class PriceCacheRepository(ABC):
    """Stores and retrieves cached OHLCV price bars."""

    @abstractmethod
    def save_bars(self, bars: list[PriceBar]) -> int:
        """Save price bars to the cache.

        Uses UPSERT semantics — bars with the same (symbol, source,
        interval, timestamp) are replaced rather than duplicated.

        Args:
            bars: List of PriceBar domain entities.

        Returns:
            Number of bars saved (new + updated).
        """
        ...

    @abstractmethod
    def query_bars(
        self,
        symbol: str,
        source: str,
        interval: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[PriceBar]:
        """Retrieve cached price bars.

        Args:
            symbol: Ticker symbol.
            source: Data source ('yfinance', 'hyperliquid').
            interval: Time interval.
            start_date: Optional start filter (ISO format, inclusive).
            end_date: Optional end filter (ISO format, inclusive).

        Returns:
            List of PriceBar entities, ordered by timestamp ascending.
        """
        ...

    @abstractmethod
    def delete_bars(
        self,
        symbol: str,
        source: str | None = None,
        interval: str | None = None,
        before_date: str | None = None,
    ) -> int:
        """Delete cached price bars.

        Symbol is required. Other params narrow the deletion scope.

        Args:
            symbol: Ticker symbol (required).
            source: Optional source filter.
            interval: Optional interval filter.
            before_date: Optional — delete bars before this date (ISO format).

        Returns:
            Number of bars deleted.
        """
        ...

    @abstractmethod
    def list_symbols(self, source: str | None = None) -> list[str]:
        """List distinct symbols in the cache.

        Args:
            source: Optional source filter.

        Returns:
            Sorted list of unique symbol strings.
        """
        ...

    @abstractmethod
    def get_latest_bar(
        self,
        symbol: str,
        source: str,
        interval: str,
    ) -> PriceBar | None:
        """Get the most recent bar for a symbol/source/interval.

        Args:
            symbol: Ticker symbol.
            source: Data source.
            interval: Time interval.

        Returns:
            Latest PriceBar or None if no data.
        """
        ...
