"""Warning rule defaults for strategy validation."""

from finbar_strategy_runtime.parser.no_exit_warning_rule import NoExitWarningRule
from finbar_strategy_runtime.parser.no_stop_warning_rule import NoStopWarningRule
from finbar_strategy_runtime.parser.strategy_warning_rule import StrategyWarningRule

DEFAULT_WARNING_RULES: list[StrategyWarningRule] = [
    NoExitWarningRule(),
    NoStopWarningRule(),
]
