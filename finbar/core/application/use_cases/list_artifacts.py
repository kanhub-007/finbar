"""ListArtifactsUseCase — discover stored bar artifacts."""

from finbar.core.application.dto.artifact_metadata import ArtifactMetadata
from finbar.core.application.dto.list_artifacts_result import ListArtifactsResult
from finbar.core.domain.interfaces.indicator_artifact_provider import (
    IndicatorArtifactProvider,
)


class ListArtifactsUseCase:
    """List persisted indicator artifacts without returning bar payloads."""

    def __init__(self, provider: IndicatorArtifactProvider):
        """Create the use case with an artifact provider."""
        self._provider = provider

    def execute(
        self,
        symbol: str | None = None,
        source: str | None = None,
        interval: str | None = None,
    ) -> ListArtifactsResult:
        """Return artifact metadata matching optional filters."""
        try:
            items = self._provider.list_artifacts(symbol, source, interval)
        except Exception as exc:
            return ListArtifactsResult(error=str(exc))
        return ListArtifactsResult(
            artifacts=[_metadata_from_dict(item) for item in items]
        )


def _metadata_from_dict(item: dict) -> ArtifactMetadata:
    """Convert provider metadata into an application DTO."""
    return ArtifactMetadata(**item)
