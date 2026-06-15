"""RecordingIndicatorJobManager — in-memory fake for use-case tests.

Records every started job's request params without spawning any async task,
so synchronous use-case tests can assert on what was requested.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from finbar.core.domain.entities.indicator_job import IndicatorJob
from finbar.core.domain.interfaces.indicator_job_manager import IndicatorJobManager


class RecordingIndicatorJobManager(IndicatorJobManager):
    """In-memory fake that records every started job's params.

    Jobs are keyed by ``timeframe_alias`` for easy inspection. The supplied
    runner is never called, keeping tests synchronous and focused on the
    request payload rather than the execution.
    """

    def __init__(self) -> None:
        """Create an empty recording manager."""
        self.started_params: dict[str, dict[str, Any]] = {}
        self.started_jobs: dict[str, IndicatorJob] = {}

    def start(
        self,
        params: dict[str, Any],
        runner: Callable[[IndicatorJob], Awaitable[None]],
    ) -> IndicatorJob:
        """Record the request params and return a job without running it."""
        alias = str(params.get("timeframe_alias", "primary"))
        job = IndicatorJob(
            job_id=alias,
            symbol=params.get("symbol", ""),
            source=params.get("source", "yfinance"),
            interval=params.get("interval", "1d"),
            mode=params.get("mode", "selected"),
            timeframe_alias=alias,
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
            metadata=dict(params),
        )
        self.started_params[alias] = dict(params)
        self.started_jobs[alias] = job
        return job

    def get(self, job_id: str) -> IndicatorJob | None:
        """Return a job by its alias-keyed id."""
        return self.started_jobs.get(job_id)

    def update(self, job: IndicatorJob, **updates: Any) -> None:
        """Apply updates to a recorded job."""
        for key, value in updates.items():
            setattr(job, key, value)

    def store_result(self, job: IndicatorJob, bars: list[dict]) -> None:
        """No-op: results are not needed for request-payload tests."""

    def get_result_page(
        self,
        job_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int, int, int]:
        """Return an empty page."""
        return [], page, page_size, 0

    def cancel(self, job_id: str) -> IndicatorJob | None:
        """Return the recorded job without spawning cancellation."""
        return self.started_jobs.get(job_id)
