"""StrategyWarningRule — interface for detecting strategy issues."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.strategy_definition_v2 import StrategyDefinitionV2
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)


class StrategyWarningRule(ABC):
    """Detect a specific category of strategy issue during validation."""

    @abstractmethod
    def check(self, definition: StrategyDefinitionV2) -> StrategyValidationError | None:
        """Return a warning if the issue is detected, or None."""
        ...
