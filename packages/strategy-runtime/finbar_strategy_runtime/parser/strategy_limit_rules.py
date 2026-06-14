"""Limit rule defaults for strategy validation."""

from finbar_strategy_runtime.parser.max_condition_depth_limit_rule import (
    MaxConditionDepthLimitRule,
)
from finbar_strategy_runtime.parser.max_features_limit_rule import (
    MaxFeaturesLimitRule,
)
from finbar_strategy_runtime.parser.max_indicators_limit_rule import (
    MaxIndicatorsLimitRule,
)
from finbar_strategy_runtime.parser.max_parameters_limit_rule import (
    MaxParametersLimitRule,
)
from finbar_strategy_runtime.parser.strategy_limit_rule import StrategyLimitRule

DEFAULT_LIMIT_RULES: list[StrategyLimitRule] = [
    MaxParametersLimitRule(),
    MaxIndicatorsLimitRule(),
    MaxFeaturesLimitRule(),
    MaxConditionDepthLimitRule(),
]
