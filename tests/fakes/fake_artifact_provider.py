"""FakeArtifactProvider test double for enrichment artifact tests."""

from finbar.core.domain.entities.indicator_job import IndicatorJob


class FakeArtifactProvider:
    """In-memory artifact provider for backtest tests."""

    def __init__(
        self,
        artifacts: dict[str, list[dict]],
        statuses: dict[str, str] | None = None,
        metadata: dict[str, dict] | None = None,
    ):
        """Create a fake provider with artifact bars, statuses, and metadata."""
        self._artifacts = artifacts
        self._jobs = {
            job_id: IndicatorJob(
                job_id=job_id,
                status=(statuses or {}).get(job_id, "completed"),
                metadata=(metadata or {}).get(job_id, {}),
            )
            for job_id in artifacts
        }

    def get_artifact_job(self, job_id: str):
        """Return fake job metadata."""
        return self._jobs.get(job_id)

    def get_artifact_bars(self, job_id: str) -> list[dict] | None:
        """Return fake artifact bars."""
        return self._artifacts.get(job_id)
