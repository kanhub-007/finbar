"""DeleteStrategyDefinitionRequest — DTO for deleting a v2 strategy document."""

from dataclasses import dataclass


@dataclass
class DeleteStrategyDefinitionRequest:
    """Request DTO for the DeleteStrategyDefinition use case."""

    name: str
    """Name of the strategy document to delete."""
