"""Factory for compiling v2 JSON definitions into executable strategies."""

from finbar.core.domain.entities.strategy_definition_v2 import StrategyDefinitionV2
from finbar.core.domain.interfaces.strategy_definition_strategy_factory import (
    StrategyDefinitionStrategyFactory,
)
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.json_rule_based_strategy import (
    JsonRuleBasedStrategy,
)


class JsonStrategyDefinitionStrategyFactory(StrategyDefinitionStrategyFactory):
    """Create JsonRuleBasedStrategy instances from canonical v2 definitions."""

    def create(self, definition: StrategyDefinitionV2) -> TradingStrategy:
        """Return a fresh executable strategy instance."""
        return JsonRuleBasedStrategy(definition)
