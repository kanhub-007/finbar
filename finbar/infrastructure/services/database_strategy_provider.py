"""DatabaseStrategyProvider — creates user-defined rule-based strategies."""

from finbar.core.domain.entities.strategy_meta import StrategyMeta
from finbar.core.domain.interfaces.strategy_definition_repository import (
    StrategyDefinitionRepository,
)
from finbar.core.domain.interfaces.strategy_provider import StrategyProvider
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.rule_based_strategy import RuleBasedStrategy


class DatabaseStrategyProvider(StrategyProvider):
    """Resolves user-defined strategies stored in a StrategyDefinitionRepository."""

    def __init__(self, repository: StrategyDefinitionRepository):
        """Initialize with a strategy-definition repository."""
        self._repository = repository

    def create(self, name: str, params: dict | None = None) -> TradingStrategy | None:
        """Create a rule-based strategy from its stored definition.

        Args:
            name: Strategy name.
            params: Ignored for stored strategies; definitions carry parameters.
        """
        definition = self._repository.find_by_name(name)
        if definition is None:
            return None
        return RuleBasedStrategy(definition)

    def list_metadata(self) -> list[StrategyMeta]:
        """List metadata for all stored user-defined strategies."""
        return [
            RuleBasedStrategy(definition).meta()
            for definition in self._repository.list_all()
        ]

    def exists(self, name: str) -> bool:
        """Return True if a user-defined strategy exists."""
        return self._repository.find_by_name(name) is not None
