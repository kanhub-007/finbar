"""MaxIndicatorsLimitRule — limit the number of declared indicators."""

from finbar.core.application.services.strategy_limit_rule import StrategyLimitRule
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)


class MaxIndicatorsLimitRule(StrategyLimitRule):
    """Reject strategies with more than the allowed number of indicators."""

    def __init__(self, maximum: int = 20):
        self._maximum = maximum

    def check(self, definition, params, indicators, features):
        if len(indicators) > self._maximum:
            return StrategyValidationError(
                path="$.indicators",
                message=f"max {self._maximum} indicators (got {len(indicators)})",
            )
        return None
