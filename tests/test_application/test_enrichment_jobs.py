"""Tests for asynchronous enrichment job use cases."""

import pytest

from finbar.core.application.dto.start_indicator_job_request import (
    StartIndicatorJobRequest,
)
from finbar.core.application.use_cases.cancel_indicator_job import (
    CancelIndicatorJobUseCase,
)
from finbar.core.application.use_cases.get_indicator_job_progress import (
    GetIndicatorJobProgressUseCase,
)
from finbar.core.application.use_cases.get_indicator_job_results import (
    GetIndicatorJobResultsUseCase,
)
from finbar.core.application.use_cases.start_indicator_job import (
    StartIndicatorJobUseCase,
)
from finbar.core.domain.entities.indicator_job import IndicatorJob
from finbar.infrastructure.services.in_memory_indicator_job_manager import (
    InMemoryIndicatorJobManager,
)


class NoopIndicatorJobRunner:
    """Test runner that leaves queued jobs untouched."""

    async def run(self, job: IndicatorJob) -> None:
        """No-op async job runner for manager tests."""


def _start_use_case(manager: InMemoryIndicatorJobManager) -> StartIndicatorJobUseCase:
    return StartIndicatorJobUseCase(manager, NoopIndicatorJobRunner())


@pytest.mark.asyncio
async def test_start_indicator_job_records_request_metadata():
    """Starting a job stores normalized request metadata."""
    manager = InMemoryIndicatorJobManager()
    request = StartIndicatorJobRequest(
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
    result = GetIndicatorJobProgressUseCase(InMemoryIndicatorJobManager()).execute(
        "missing"
    )

    assert result.found is False
    assert result.job_id == "missing"


@pytest.mark.asyncio
async def test_results_are_paginated_for_completed_job():
    """Completed job artifacts are returned one page at a time."""
    manager = InMemoryIndicatorJobManager()
    job = _start_use_case(manager).execute(StartIndicatorJobRequest(symbol="AAPL"))
    bars = [{"timestamp": f"2024-01-{day:02d}", "close": day} for day in range(1, 6)]
    manager.store_result(job, bars)
    manager.update(job, status="completed")

    result = GetIndicatorJobResultsUseCase(manager).execute(
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
    manager = InMemoryIndicatorJobManager()
    job = _start_use_case(manager).execute(StartIndicatorJobRequest(symbol="AAPL"))

    result = GetIndicatorJobResultsUseCase(manager).execute(job.job_id)

    assert result.found is True
    assert result.status == "queued"
    assert result.error == "Job is not complete (status: queued)"


@pytest.mark.asyncio
async def test_cancel_indicator_job_updates_status():
    """Cancel use case cancels queued/running jobs through the manager."""
    manager = InMemoryIndicatorJobManager()
    job = _start_use_case(manager).execute(StartIndicatorJobRequest(symbol="AAPL"))

    result = CancelIndicatorJobUseCase(manager).execute(job.job_id)

    assert result.found is True
    assert result.status == "cancelled"
    assert result.error == "Cancelled by user"
