"""DescribeArtifactResult — artifact metadata detail result DTO."""

from dataclasses import dataclass

from finbar.core.application.dto.artifact_metadata import ArtifactMetadata


@dataclass(frozen=True)
class DescribeArtifactResult:
    """Result containing one artifact's metadata and diagnostics."""

    found: bool
    """True when the artifact exists."""

    artifact: ArtifactMetadata | None = None
    """Artifact metadata if found."""

    error: str | None = None
    """Error message if lookup failed."""
