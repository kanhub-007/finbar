"""ListArtifactsResult — artifact discovery result DTO."""

from dataclasses import dataclass, field

from finbar.core.application.dto.artifact_metadata import ArtifactMetadata


@dataclass(frozen=True)
class ListArtifactsResult:
    """Result containing artifact metadata records."""

    artifacts: list[ArtifactMetadata] = field(default_factory=list)
    """Artifacts matching the query."""

    error: str | None = None
    """Error message if discovery failed."""
