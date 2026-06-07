"""Tests for parameter optimization grid search."""

import pytest

from finbar.core.application.dto.start_optimization_job_request import (
    StartOptimizationJobRequest,
)
from finbar.core.application.services.strategy_definition_parser import (
    StrategyDefinitionParser,
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
from finbar.core.domain.entities.optimizer_config import OptimizerConfig
from finbar.core.domain.entities.param_range import ParamRange
from finbar.core.domain.interfaces.indicator_artifact_provider import (
    IndicatorArtifactProvider,
)
from finbar.core.domain.interfaces.optimization_job_manager import (
    OptimizationJobManager,
)
from finbar.core.domain.interfaces.optimization_job_runner import (
    OptimizationJobRunner,
)
from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.grid_search_optimizer import (
    GridSearchOptimizer,
    _execution_params,
    _generate_combinations,
    _parse_ranges,
    _warmup_error,
)
from finbar.infrastructure.services.in_memory_optimization_job_manager import (
    InMemoryOptimizationJobManager,
)
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar.infrastructure.services.strategy_definition_factory import (
    StrategyDefinitionFactory,
)


class _NoopRunner(OptimizationJobRunner):
    """Test double that leaves queued jobs unchanged."""

    async def run(self, job: OptimizationJob) -> None:
        """No-op for manager tests."""


class _ArtifactProvider(IndicatorArtifactProvider):
    """Test artifact provider backed by an in-memory dict."""

    def __init__(self, bars_by_id: dict[str, list[dict]]):
        self._bars_by_id = bars_by_id

    def get_artifact_job(self, job_id: str):
        """Return no job metadata; optimizer only needs bars."""
        return None

    def get_artifact_bars(self, job_id: str) -> list[dict] | None:
        """Return bars for an artifact id."""
        return self._bars_by_id.get(job_id)


class _SyncManager(OptimizationJobManager):
    """Synchronous manager used to inspect optimizer updates."""

    def start(self, params: dict, runner):
        """Create a job without launching a background task."""
        return OptimizationJob(
            job_id="sync-job",
            metric=params.get("metric", "sharpe_ratio"),
            metadata=dict(params),
        )

    def get(self, job_id: str) -> OptimizationJob | None:
        """No lookup support needed for this test double."""
        return None

    def update(self, job: OptimizationJob, **updates) -> None:
        """Apply updates directly to the supplied job."""
        for key, value in updates.items():
            setattr(job, key, value)

    def cancel(self, job_id: str) -> OptimizationJob | None:
        """No cancellation support needed for this test double."""
        return None


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


class TestOptimizationPreparation:
    def test_warmup_error_blocks_missing_after_warmup(self):
        """Optimizer uses same missing-after-warmup blocking policy."""
        warmup = {
            "no_tradable_bars": False,
            "missing_after_warmup": ["sma_20"],
        }

        assert _warmup_error(warmup) == "Missing required data after warmup: sma_20"

    def test_execution_params_include_backtest_controls(self):
        """Optimizer passes execution controls through to the engine."""
        params = _execution_params(
            {
                "interval": "1h",
                "risk_per_trade": 0.03,
                "leverage": 2,
                "risk_mode": "leverage_scaled_risk",
                "commission_pct": 0.001,
                "slippage_pct": 0.002,
                "cap_explicit_size": False,
                "reject_oversized_explicit_orders": True,
                "allow_negative_cash": True,
                "market_calendar": "crypto_24_7",
            }
        )

        assert params["interval"] == "1h"
        assert params["risk_per_trade"] == 0.03
        assert params["leverage"] == 2
        assert params["risk_mode"] == "leverage_scaled_risk"
        assert params["commission_pct"] == 0.001
        assert params["slippage_pct"] == 0.002
        assert params["cap_explicit_size"] is False
        assert params["reject_oversized_explicit_orders"] is True
        assert params["allow_negative_cash"] is True
        assert params["market_calendar"] == "crypto_24_7"


class TestOptimizationParity:
    def test_single_combination_matches_direct_backtest_metrics(self):
        """A one-combination optimization matches direct engine metrics."""
        bars = [
            _bar("2024-01-01", 100, 100),
            _bar("2024-01-02", 100, 100),
            _bar("2024-01-03", 110, 110),
        ]
        definition = _always_long_strategy()
        manager = _SyncManager()
        converter = PandasBarFrameConverter()
        parser = StrategyDefinitionParser()
        factory = StrategyDefinitionFactory()
        engine = BacktestRunner()
        optimizer = GridSearchOptimizer(
            OptimizerConfig(
                parser=parser,
                engine=engine,
                converter=converter,
                strategy_factory=factory,
                manager=manager,
                artifact_provider=_ArtifactProvider({"bars": bars}),
            )
        )
        job = OptimizationJob(
            job_id="opt-1",
            metric="total_return",
            metadata={
                "definition": definition,
                "bars_artifact_id": "bars",
                "param_ranges": {},
                "metric": "total_return",
                "interval": "1d",
                "initial_cash": 10000,
                "commission_pct": 0.001,
            },
        )

        optimizer._sync_run(job)
        validation = parser.parse(definition, {})
        strategy = factory.create(validation.definition)
        direct = engine.run(
            converter.bars_to_frame(bars),
            strategy,
            10000,
            interval="1d",
            commission_pct=0.001,
        )

        assert job.status == "completed"
        assert len(job.results) == 1
        assert job.results[0].total_return == direct["total_return"]
        assert job.results[0].total_trades == direct["total_trades"]
        assert job.results[0].win_rate == direct["win_rate"]


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

    @pytest.mark.asyncio
    async def test_start_job_records_execution_metadata(self):
        """Starting a job stores backtest execution controls."""
        manager = InMemoryOptimizationJobManager()
        use_case = StartOptimizationJobUseCase(manager, _NoopRunner())

        job = use_case.execute(
            StartOptimizationJobRequest(
                definition={},
                bars_artifact_id="primary-123",
                param_ranges={},
                leverage=3,
                risk_mode="leverage_scaled_risk",
                commission_pct=0.001,
                slippage_pct=0.002,
                cap_explicit_size=False,
                reject_oversized_explicit_orders=True,
                allow_negative_cash=True,
                market_calendar="crypto_24_7",
            )
        )

        assert job.metadata["leverage"] == 3
        assert job.metadata["risk_mode"] == "leverage_scaled_risk"
        assert job.metadata["commission_pct"] == 0.001
        assert job.metadata["slippage_pct"] == 0.002
        assert job.metadata["cap_explicit_size"] is False
        assert job.metadata["reject_oversized_explicit_orders"] is True
        assert job.metadata["allow_negative_cash"] is True
        assert job.metadata["market_calendar"] == "crypto_24_7"

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


def _bar(timestamp: str, open_price: float, close: float) -> dict:
    """Return a minimal OHLCV bar dict."""
    high = max(open_price, close)
    low = min(open_price, close)
    return {
        "timestamp": timestamp,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000000,
    }


def _always_long_strategy() -> dict:
    """Return a JSON strategy that enters long whenever close is positive."""
    return {
        "schema_version": "2.0",
        "name": "always_long",
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "operator": ">",
                        "left": "close",
                        "right": 0,
                    }
                }
            }
        },
    }
