"""Factory for compiling JSON definitions into executable strategies."""

from finbar_strategy_runtime.domain.entities.strategy_definition import StrategyDefinition
from finbar_strategy_runtime.domain.interfaces.strategy_definition_strategy_factory import (
    StrategyDefinitionStrategyFactory,
)
from finbar_strategy_runtime.domain.interfaces.trading_strategy import TradingStrategy
from finbar_strategy_runtime.evaluation.json_rule_based_strategy import (
    JsonRuleBasedStrategy,
)


class StrategyDefinitionFactory(StrategyDefinitionStrategyFactory):
    """Create JsonRuleBasedStrategy instances from canonical definitions."""

    def create(self, definition: StrategyDefinition) -> TradingStrategy:
        """Return a fresh executable strategy instance."""
        return JsonRuleBasedStrategy(definition)
