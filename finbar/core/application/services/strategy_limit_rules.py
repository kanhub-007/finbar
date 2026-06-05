"""Limit rule defaults for strategy validation."""

from finbar.core.application.services.max_condition_depth_limit_rule import (
    MaxConditionDepthLimitRule,
)
from finbar.core.application.services.max_features_limit_rule import (
    MaxFeaturesLimitRule,
)
from finbar.core.application.services.max_indicators_limit_rule import (
    MaxIndicatorsLimitRule,
)
from finbar.core.application.services.max_parameters_limit_rule import (
    MaxParametersLimitRule,
)
from finbar.core.application.services.strategy_limit_rule import StrategyLimitRule

DEFAULT_LIMIT_RULES: list[StrategyLimitRule] = [
    MaxParametersLimitRule(),
    MaxIndicatorsLimitRule(),
    MaxFeaturesLimitRule(),
    MaxConditionDepthLimitRule(),
]
