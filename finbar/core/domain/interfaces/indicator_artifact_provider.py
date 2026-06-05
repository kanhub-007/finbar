"""IndicatorArtifactProvider interface for reading indicator artifacts."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.indicator_job import IndicatorJob


class IndicatorArtifactProvider(ABC):
    """Read completed indicator job metadata and stored bar artifacts."""

    @abstractmethod
    def get_artifact_job(self, job_id: str) -> IndicatorJob | None:
        """Return metadata for an indicator artifact job."""
        ...

    @abstractmethod
    def get_artifact_bars(self, job_id: str) -> list[dict] | None:
        """Return all bars for an indicator artifact, or None if missing."""
        ...
