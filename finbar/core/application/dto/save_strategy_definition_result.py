"""SaveStrategyDefinitionResult — result DTO for saving a strategy document."""

from dataclasses import dataclass, field

from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)


@dataclass
class SaveStrategyDefinitionResult:
    """Result of attempting to save a strategy document."""

    saved: bool
    name: str = ""
    schema_version: str = ""
    error: str = ""
    validation_errors: list[StrategyValidationError] = field(default_factory=list)
