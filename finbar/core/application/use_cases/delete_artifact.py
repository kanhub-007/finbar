"""DeleteArtifactUseCase — explicitly remove a stored artifact."""

from finbar.core.application.dto.delete_artifact_result import DeleteArtifactResult
from finbar.core.domain.interfaces.indicator_artifact_provider import (
    IndicatorArtifactProvider,
)


class DeleteArtifactUseCase:
    """Delete a persisted artifact by ID when explicitly requested."""

    def __init__(self, provider: IndicatorArtifactProvider):
        """Create the use case with an artifact provider."""
        self._provider = provider

    def execute(self, artifact_id: str) -> DeleteArtifactResult:
        """Delete one artifact and return whether it existed."""
        try:
            deleted = self._provider.delete_artifact(artifact_id)
        except Exception as exc:
            return DeleteArtifactResult(
                deleted=False,
                artifact_id=artifact_id,
                error=str(exc),
            )
        return DeleteArtifactResult(deleted=deleted, artifact_id=artifact_id)
