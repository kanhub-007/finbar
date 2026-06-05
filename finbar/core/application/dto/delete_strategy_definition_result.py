"""DeleteStrategyDefinitionResult — result DTO for deleting a strategy document."""

from dataclasses import dataclass


@dataclass
class DeleteStrategyDefinitionResult:
    """Result of attempting to delete a strategy document."""

    deleted: bool
    """True if the document was found and deleted."""

    name: str = ""
    """Name of the strategy that was deleted or attempted."""

    error: str = ""
    """Error message when deletion fails for reasons other than not found."""
