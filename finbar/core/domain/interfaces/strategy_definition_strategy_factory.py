"""Factory interface for compiling v2 definitions into TradingStrategy objects."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.strategy_definition import StrategyDefinition
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy


class StrategyDefinitionStrategyFactory(ABC):
    """Create executable TradingStrategy instances from v2 definitions."""

    @abstractmethod
    def create(self, definition: StrategyDefinition) -> TradingStrategy:
        """Compile a validated v2 definition into a fresh strategy instance."""
