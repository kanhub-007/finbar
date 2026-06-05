"""SaveStrategyDefinitionRequest — DTO for saving a strategy document."""

from dataclasses import dataclass


@dataclass
class SaveStrategyDefinitionRequest:
    """Request DTO for the SaveStrategyDefinition use case."""

    definition_json: str
    name_override: str | None = None
