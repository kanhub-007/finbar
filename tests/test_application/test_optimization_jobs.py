"""Tests for parameter optimization grid search."""

import pytest

from finbar.core.application.dto.start_optimization_job_request import (
    StartOptimizationJobRequest,
)
from finbar.core.application.use_cases.cancel_optimization_job import (
    CancelOptimizationJobUseCase,
)
from finbar.core.application.use_cases.get_optimization_job_progress import (
    GetOptimizationJobProgressUseCase,
)
from finbar.core.application.use_cases.get_optimization_job_results import (
    GetOptimizationJobResultsUseCase,
)
from finbar.core.application.use_cases.start_optimization_job import (
    StartOptimizationJobUseCase,
)
from finbar.core.domain.entities.optimization_job import OptimizationJob
from finbar.core.domain.entities.param_range import ParamRange
from finbar.core.domain.interfaces.optimization_job_runner import (
    OptimizationJobRunner,
)
from finbar.infrastructure.services.grid_search_optimizer import (
    _generate_combinations,
    _parse_ranges,
)
from finbar.infrastructure.services.in_memory_optimization_job_manager import (
    InMemoryOptimizationJobManager,
)


class _NoopRunner(OptimizationJobRunner):
    """Test double that leaves queued jobs unchanged."""

    async def run(self, job: OptimizationJob) -> None:
        """No-op for manager tests."""


class TestParamRange:
    def test_generates_integer_steps(self):
        """Integer steps generate correct values."""
        r = ParamRange(min=10, max=50, step=10)

        assert r.values() == [10.0, 20.0, 30.0, 40.0, 50.0]

    def test_generates_float_steps(self):
        """Float steps generate correct values."""
        r = ParamRange(min=1.0, max=3.0, step=0.5)

        assert r.values() == [1.0, 1.5, 2.0, 2.5, 3.0]

    def test_single_value_range(self):
        """Min==max produces one value."""
        r = ParamRange(min=20, max=20, step=5)

        assert r.values() == [20.0]

    def test_count_matches_values(self):
        """Count matches the number of generated values."""
        r = ParamRange(min=1, max=10, step=3)

        assert r.count() == len(r.values())


class TestGridSearchCombinatorics:
    def test_parse_ranges_from_dict(self):
        """Param range dicts are parsed into ParamRange objects."""
        raw = {
            "fast": {"min": 10, "max": 30, "step": 10},
            "slow": {"min": 50, "max": 100, "step": 50},
        }

        ranges = _parse_ranges(raw)

        assert len(ranges) == 2
        assert ranges["fast"].values() == [10.0, 20.0, 30.0]
        assert ranges["slow"].values() == [50.0, 100.0]

    def test_generates_cartesian_product(self):
        """Combinations are the Cartesian product of all range values."""
        ranges = {
            "a": ParamRange(min=1, max=3, step=1),
            "b": ParamRange(min=10, max=20, step=10),
        }

        combos = _generate_combinations(ranges)

        assert len(combos) == 6
        assert {"a": 1.0, "b": 10.0} in combos
        assert {"a": 3.0, "b": 20.0} in combos

    def test_empty_ranges_returns_single_empty_combo(self):
        """No ranges produces a single empty combination."""
        assert _generate_combinations({}) == [{}]


class TestOptimizationJobManager:
    @pytest.mark.asyncio
    async def test_start_job_records_metadata(self):
        """Starting a job stores metric and metadata."""
        manager = InMemoryOptimizationJobManager()
        use_case = StartOptimizationJobUseCase(manager, _NoopRunner())

        job = use_case.execute(
            StartOptimizationJobRequest(
                definition={},
                bars_artifact_id="primary-123",
                param_ranges={"p": {"min": 1, "max": 3, "step": 1}},
                metric="sortino_ratio",
            )
        )

        assert job.job_id
        assert job.metric == "sortino_ratio"
        assert job.metadata["bars_artifact_id"] == "primary-123"

    def test_progress_not_found(self):
        """Missing jobs produce structured not-found result."""
        result = GetOptimizationJobProgressUseCase(
            InMemoryOptimizationJobManager()
        ).execute("missing")

        assert result.found is False

    @pytest.mark.asyncio
    async def test_results_require_completed(self):
        """Non-completed jobs return structured error."""
        manager = InMemoryOptimizationJobManager()
        use_case = StartOptimizationJobUseCase(manager, _NoopRunner())
        job = use_case.execute(
            StartOptimizationJobRequest(
                definition={},
                bars_artifact_id="abc",
                param_ranges={"p": {"min": 1, "max": 2, "step": 1}},
            )
        )

        result = GetOptimizationJobResultsUseCase(manager).execute(job.job_id)

        assert result.found is True
        assert result.status == "queued"
        assert result.error == "Job is not complete (status: queued)"

    @pytest.mark.asyncio
    async def test_cancel_job(self):
        """Cancel updates status and error."""
        manager = InMemoryOptimizationJobManager()
        use_case = StartOptimizationJobUseCase(manager, _NoopRunner())
        job = use_case.execute(
            StartOptimizationJobRequest(
                definition={},
                bars_artifact_id="abc",
                param_ranges={"p": {"min": 1, "max": 2, "step": 1}},
            )
        )

        result = CancelOptimizationJobUseCase(manager).execute(job.job_id)

        assert result.found is True
        assert result.status == "cancelled"
        assert result.error == "Cancelled by user"
