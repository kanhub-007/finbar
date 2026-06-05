"""NoExitWarningRule — warn when a side has no exit condition."""

from finbar.core.application.services.strategy_warning_rule import StrategyWarningRule
from finbar.core.domain.entities.strategy_definition import StrategyDefinition
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)


class NoExitWarningRule(StrategyWarningRule):
    """Warn when a trading side has no exit condition defined."""

    def check(self, definition: StrategyDefinition) -> StrategyValidationError | None:
        for side, rules in definition.sides.items():
            if rules.exit is None:
                return StrategyValidationError(
                    path=f"$.sides.{side}",
                    message=f"no exit condition defined for {side} side",
                    code="no_exit",
                )
        return None
