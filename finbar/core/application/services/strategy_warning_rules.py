"""Warning rule defaults for v2 strategy validation."""

from finbar.core.application.services.no_exit_warning_rule import NoExitWarningRule
from finbar.core.application.services.no_stop_warning_rule import NoStopWarningRule
from finbar.core.application.services.strategy_warning_rule import StrategyWarningRule

DEFAULT_WARNING_RULES: list[StrategyWarningRule] = [
    NoExitWarningRule(),
    NoStopWarningRule(),
]
