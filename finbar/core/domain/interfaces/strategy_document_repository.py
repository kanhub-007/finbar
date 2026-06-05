"""StrategyDocumentRepository — persistence interface for strategy documents."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.strategy_document import StrategyDocument


class StrategyDocumentRepository(ABC):
    """Repository for persisted JSON strategy documents."""

    @abstractmethod
    def save(self, document: StrategyDocument) -> None:
        """Insert or update a strategy document.

        Args:
            document: The StrategyDocument to persist.
        """
        ...

    @abstractmethod
    def find_by_name(self, name: str) -> StrategyDocument | None:
        """Retrieve a strategy document by name.

        Args:
            name: Strategy name.

        Returns:
            StrategyDocument or None if not found.
        """
        ...

    @abstractmethod
    def list_all(self) -> list[StrategyDocument]:
        """List all strategy documents.

        Returns:
            List of StrategyDocument objects, sorted by name.
        """
        ...

    @abstractmethod
    def delete(self, name: str) -> bool:
        """Delete a strategy document by name.

        Args:
            name: Strategy name.

        Returns:
            True if deleted, False if not found.
        """
        ...
