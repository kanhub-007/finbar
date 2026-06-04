"""GetSymbolInfoUseCase — fetch and cache asset/company metadata.

Flow: call StockDataFetcher.fetch_info() → save to SymbolInfoRepository
→ return SymbolInfo.
"""

import logging

from finbar.core.domain.entities.symbol_info import SymbolInfo
from finbar.core.domain.interfaces.stock_data_fetcher import StockDataFetcher
from finbar.core.domain.interfaces.symbol_info_repository import (
    SymbolInfoRepository,
)

logger = logging.getLogger(__name__)


class GetSymbolInfoUseCase:
    """Look up symbol metadata, cache it, and return it."""

    def __init__(
        self,
        fetcher: StockDataFetcher,
        info_repo: SymbolInfoRepository,
    ):
        self._fetcher = fetcher
        self._info_repo = info_repo

    def execute(self, symbol: str) -> SymbolInfo | None:
        """Fetch and cache symbol metadata.

        Checks cache first; if missing or stale, fetches from source.

        Args:
            symbol: Ticker symbol.

        Returns:
            SymbolInfo or None if not found.
        """
        # Check cache first
        cached = self._info_repo.find_by_symbol(symbol)
        if cached:
            return cached

        # Fetch from source
        info = self._fetcher.fetch_info(symbol)
        if info is None:
            logger.warning("No symbol info found for %s", symbol)
            return None

        self._info_repo.save(info)
        logger.info("Cached symbol info for %s", symbol)
        return info
