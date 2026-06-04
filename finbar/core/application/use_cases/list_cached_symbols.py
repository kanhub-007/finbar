"""ListCachedSymbolsUseCase — list distinct symbols in the cache.

Thin wrapper over PriceCacheRepository.list_symbols().
"""

import logging

from finbar.core.domain.interfaces.price_cache_repository import (
    PriceCacheRepository,
)

logger = logging.getLogger(__name__)


class ListCachedSymbolsUseCase:
    """Return distinct symbols stored in the local cache."""

    def __init__(self, cache: PriceCacheRepository):
        self._cache = cache

    def execute(self, source: str | None = None) -> list[str]:
        """List cached symbols, optionally filtered by source.

        Args:
            source: Optional source filter.

        Returns:
            Sorted list of unique symbol strings.
        """
        return self._cache.list_symbols(source=source)
