"""MaxFeaturesLimitRule — limit the number of declared features."""

from finbar.core.application.services.strategy_limit_rule import StrategyLimitRule
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)


class MaxFeaturesLimitRule(StrategyLimitRule):
    """Reject strategies with more than the allowed number of features."""

    def __init__(self, maximum: int = 20):
        self._maximum = maximum

    def check(self, definition, params, indicators, features):
        if len(features) > self._maximum:
            return StrategyValidationError(
                path="$.features",
                message=f"max {self._maximum} features (got {len(features)})",
            )
        return None
