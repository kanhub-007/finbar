"""Factory interface for compiling definitions into TradingStrategy objects."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.strategy_definition import StrategyDefinition
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy


class StrategyDefinitionStrategyFactory(ABC):
    """Create executable TradingStrategy instances from canonical definitions."""

    @abstractmethod
    def create(self, definition: StrategyDefinition) -> TradingStrategy:
        """Compile a validated definition into a fresh strategy instance."""
