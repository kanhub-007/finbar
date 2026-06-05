"""EnrichmentArtifactProvider interface for reading enrichment artifacts."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.enrichment_job import EnrichmentJob


class EnrichmentArtifactProvider(ABC):
    """Read completed enrichment job metadata and stored bar artifacts."""

    @abstractmethod
    def get_artifact_job(self, job_id: str) -> EnrichmentJob | None:
        """Return metadata for an enrichment artifact job."""
        ...

    @abstractmethod
    def get_artifact_bars(self, job_id: str) -> list[dict] | None:
        """Return all bars for an enrichment artifact, or None if missing."""
        ...
