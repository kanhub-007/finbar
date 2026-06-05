"""StrategyDocumentRepository — persistence interface for v2 strategy documents."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.strategy_document import StrategyDocument


class StrategyDocumentRepository(ABC):
    """Repository for persisted v2 JSON strategy documents."""

    @abstractmethod
    def save(self, document: StrategyDocument) -> None:
        """Insert or update a v2 strategy document.

        Args:
            document: The StrategyDocument to persist.
        """
        ...

    @abstractmethod
    def find_by_name(self, name: str) -> StrategyDocument | None:
        """Retrieve a v2 strategy document by name.

        Args:
            name: Strategy name.

        Returns:
            StrategyDocument or None if not found.
        """
        ...

    @abstractmethod
    def list_all(self) -> list[StrategyDocument]:
        """List all v2 strategy documents.

        Returns:
            List of StrategyDocument objects, sorted by name.
        """
        ...

    @abstractmethod
    def delete(self, name: str) -> bool:
        """Delete a v2 strategy document by name.

        Args:
            name: Strategy name.

        Returns:
            True if deleted, False if not found.
        """
        ...
