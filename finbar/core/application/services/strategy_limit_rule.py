"""StrategyLimitRule — interface for enforcing SDK limits."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.strategy_definition_v2 import StrategyDefinitionV2
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)


class StrategyLimitRule(ABC):
    """Enforce a specific limit on v2 strategy definitions."""

    @abstractmethod
    def check(
        self,
        definition: StrategyDefinitionV2,
        params: dict,
        indicators: list,
        features: list,
    ) -> StrategyValidationError | None:
        """Return an error if the limit is exceeded, or None."""
        ...
