"""DeleteArtifactResult — explicit artifact deletion result DTO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeleteArtifactResult:
    """Result returned after an explicit artifact deletion request."""

    deleted: bool
    """True when an artifact was deleted."""

    artifact_id: str
    """Artifact identifier requested for deletion."""

    error: str | None = None
    """Error message if deletion failed."""
