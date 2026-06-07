"""IndicatorArtifactProvider interface for reading indicator artifacts."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.indicator_job import IndicatorJob


class IndicatorArtifactProvider(ABC):
    """Read and manage completed indicator job artifacts."""

    @abstractmethod
    def get_artifact_job(self, job_id: str) -> IndicatorJob | None:
        """Return metadata for an indicator artifact job."""
        ...

    @abstractmethod
    def get_artifact_bars(self, job_id: str) -> list[dict] | None:
        """Return all bars for an indicator artifact, or None if missing."""
        ...

    def list_artifacts(
        self,
        symbol: str | None = None,
        source: str | None = None,
        interval: str | None = None,
    ) -> list[dict]:
        """Return artifact metadata matching optional filters."""
        raise NotImplementedError("Artifact discovery is not supported")

    def describe_artifact(self, job_id: str) -> dict | None:
        """Return detailed artifact metadata without returning bars."""
        raise NotImplementedError("Artifact description is not supported")

    def query_artifact_bars(
        self,
        job_id: str,
        columns: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 0,
        page_size: int = 500,
    ) -> tuple[list[dict], int, int, int, int, list[str]]:
        """Return a filtered page of bars and pagination metadata."""
        raise NotImplementedError("Artifact bar queries are not supported")

    def delete_artifact(self, job_id: str) -> bool:
        """Delete an artifact explicitly. Return True if it existed."""
        raise NotImplementedError("Artifact deletion is not supported")
