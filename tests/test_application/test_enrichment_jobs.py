"""Tests for asynchronous enrichment job use cases."""

import pytest

from finbar.core.application.dto.start_enrichment_job_request import (
    StartEnrichmentJobRequest,
)
from finbar.core.application.use_cases.cancel_enrichment_job import (
    CancelEnrichmentJobUseCase,
)
from finbar.core.application.use_cases.get_enrichment_job_progress import (
    GetEnrichmentJobProgressUseCase,
)
from finbar.core.application.use_cases.get_enrichment_job_results import (
    GetEnrichmentJobResultsUseCase,
)
from finbar.core.application.use_cases.start_enrichment_job import (
    StartEnrichmentJobUseCase,
)
from finbar.core.domain.entities.enrichment_job import EnrichmentJob
from finbar.infrastructure.services.in_memory_enrichment_job_manager import (
    InMemoryEnrichmentJobManager,
)


class NoopEnrichmentJobRunner:
    """Test runner that leaves queued jobs untouched."""

    async def run(self, job: EnrichmentJob) -> None:
        """No-op async job runner for manager tests."""


def _start_use_case(manager: InMemoryEnrichmentJobManager) -> StartEnrichmentJobUseCase:
    return StartEnrichmentJobUseCase(manager, NoopEnrichmentJobRunner())


@pytest.mark.asyncio
async def test_start_enrichment_job_records_request_metadata():
    """Starting a job stores normalized request metadata."""
    manager = InMemoryEnrichmentJobManager()
    request = StartEnrichmentJobRequest(
        symbol="aapl",
        source="yfinance",
        interval="1d",
        mode="selected",
        indicators=["sma_20", "rsi_14"],
    )

    job = _start_use_case(manager).execute(request)

    assert job.job_id
    assert job.symbol == "AAPL"
    assert job.mode == "selected"
    assert job.metadata["indicators"] == ["sma_20", "rsi_14"]


def test_progress_returns_not_found_for_unknown_job():
    """Progress use case returns structured not-found result."""
    result = GetEnrichmentJobProgressUseCase(InMemoryEnrichmentJobManager()).execute(
        "missing"
    )

    assert result.found is False
    assert result.job_id == "missing"


@pytest.mark.asyncio
async def test_results_are_paginated_for_completed_job():
    """Completed job artifacts are returned one page at a time."""
    manager = InMemoryEnrichmentJobManager()
    job = _start_use_case(manager).execute(StartEnrichmentJobRequest(symbol="AAPL"))
    bars = [{"timestamp": f"2024-01-{day:02d}", "close": day} for day in range(1, 6)]
    manager.store_result(job, bars)
    manager.update(job, status="completed")

    result = GetEnrichmentJobResultsUseCase(manager).execute(
        job.job_id, page=1, page_size=2
    )

    assert result.found is True
    assert result.status == "completed"
    assert result.page == 1
    assert result.page_size == 2
    assert result.total_pages == 3
    assert result.total_bar_count == 5
    assert result.bars == bars[2:4]


@pytest.mark.asyncio
async def test_results_require_completed_job():
    """Non-completed jobs do not expose partial artifacts."""
    manager = InMemoryEnrichmentJobManager()
    job = _start_use_case(manager).execute(StartEnrichmentJobRequest(symbol="AAPL"))

    result = GetEnrichmentJobResultsUseCase(manager).execute(job.job_id)

    assert result.found is True
    assert result.status == "queued"
    assert result.error == "Job is not complete (status: queued)"


@pytest.mark.asyncio
async def test_cancel_enrichment_job_updates_status():
    """Cancel use case cancels queued/running jobs through the manager."""
    manager = InMemoryEnrichmentJobManager()
    job = _start_use_case(manager).execute(StartEnrichmentJobRequest(symbol="AAPL"))

    result = CancelEnrichmentJobUseCase(manager).execute(job.job_id)

    assert result.found is True
    assert result.status == "cancelled"
    assert result.error == "Cancelled by user"
