"""NoStopWarningRule — warn when no stop-loss is configured."""

from finbar.core.application.services.strategy_warning_rule import StrategyWarningRule
from finbar.core.domain.entities.strategy_definition import StrategyDefinition
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)


class NoStopWarningRule(StrategyWarningRule):
    """Warn when no stop-loss is configured for a strategy."""

    def check(self, definition: StrategyDefinition) -> StrategyValidationError | None:
        if definition.risk is None or definition.risk.stop_loss_type == "none":
            return StrategyValidationError(
                path="$.risk",
                message="no stop-loss defined — strategy may hold losing positions",
                code="no_stop",
            )
        return None
