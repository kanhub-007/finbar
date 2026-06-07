"""DescribeArtifactUseCase — inspect one artifact without returning bars."""

from finbar.core.application.dto.artifact_metadata import ArtifactMetadata
from finbar.core.application.dto.describe_artifact_result import DescribeArtifactResult
from finbar.core.domain.interfaces.indicator_artifact_provider import (
    IndicatorArtifactProvider,
)


class DescribeArtifactUseCase:
    """Describe a stored indicator artifact's schema and data quality."""

    def __init__(self, provider: IndicatorArtifactProvider):
        """Create the use case with an artifact provider."""
        self._provider = provider

    def execute(self, artifact_id: str) -> DescribeArtifactResult:
        """Return metadata for a single artifact."""
        try:
            item = self._provider.describe_artifact(artifact_id)
        except Exception as exc:
            return DescribeArtifactResult(found=False, error=str(exc))
        if item is None:
            return DescribeArtifactResult(found=False, error="Artifact not found")
        return DescribeArtifactResult(found=True, artifact=ArtifactMetadata(**item))
