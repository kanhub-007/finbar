"""MaxParametersLimitRule — limit the number of strategy parameters."""

from finbar.core.application.services.strategy_limit_rule import StrategyLimitRule
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)


class MaxParametersLimitRule(StrategyLimitRule):
    """Reject strategies with more than the allowed number of parameters."""

    def __init__(self, maximum: int = 20):
        self._maximum = maximum

    def check(self, definition, params, indicators, features):
        if len(params) > self._maximum:
            return StrategyValidationError(
                path="$.parameters",
                message=f"max {self._maximum} parameters (got {len(params)})",
            )
        return None
