"""SymbolInfoRepository interface — contract for persisting and querying
symbol metadata.

Repository pattern. Use cases depend on this ABC, never on a concrete
implementation.
"""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.symbol_info import SymbolInfo


class SymbolInfoRepository(ABC):
    """Stores and retrieves cached symbol/asset metadata."""

    @abstractmethod
    def save(self, info: SymbolInfo) -> None:
        """Save or update symbol metadata.

        Uses UPSERT semantics on symbol.

        Args:
            info: SymbolInfo domain entity.
        """
        ...

    @abstractmethod
    def find_by_symbol(self, symbol: str) -> SymbolInfo | None:
        """Retrieve cached metadata for a symbol.

        Args:
            symbol: Ticker symbol.

        Returns:
            SymbolInfo or None if not in cache.
        """
        ...
