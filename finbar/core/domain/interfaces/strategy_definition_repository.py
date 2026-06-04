"""StrategyDefinitionRepository — CRUD interface for user-defined strategies.

Implementations persist StrategyDefinition objects (SQLite, file, etc.).
"""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.strategy_definition import StrategyDefinition


class StrategyDefinitionRepository(ABC):
    """Repository for user-defined trading strategy definitions.

    CRUD operations for strategies stored outside the codebase.
    Built-in strategies (Python classes) are NOT managed through this
    repository — they are registered directly in the strategy registry.
    """

    @abstractmethod
    def save(self, definition: StrategyDefinition) -> None:
        """Insert or update a strategy definition.

        Args:
            definition: The StrategyDefinition to persist.
        """
        ...

    @abstractmethod
    def find_by_name(self, name: str) -> StrategyDefinition | None:
        """Retrieve a strategy definition by name.

        Args:
            name: Strategy name.

        Returns:
            StrategyDefinition or None if not found.
        """
        ...

    @abstractmethod
    def list_all(self) -> list[StrategyDefinition]:
        """List all user-defined strategy definitions.

        Returns:
            List of StrategyDefinition objects, sorted by name.
        """
        ...

    @abstractmethod
    def delete(self, name: str) -> bool:
        """Delete a strategy definition by name.

        Args:
            name: Strategy name.

        Returns:
            True if deleted, False if not found.
        """
        ...
