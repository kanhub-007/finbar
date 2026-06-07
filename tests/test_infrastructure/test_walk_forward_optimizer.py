"""Integration tests for WalkForwardOptimizer.

Uses a stub strategy and indicator artifact provider to verify the
walk-forward flow: fold splitting, grid search per fold, OOS validation,
and result aggregation.
"""

import pytest

from finbar.core.domain.entities.data_mode import DataMode
from finbar.core.domain.entities.optimization_job import OptimizationJob
from finbar.core.domain.entities.optimizer_config import OptimizerConfig
from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import StrategyMeta
from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.in_memory_optimization_job_manager import (
    InMemoryOptimizationJobManager,
)
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar.infrastructure.services.walk_forward_fold_helpers import (
    compute_fold_indices,
)
from finbar.infrastructure.services.walk_forward_optimizer import (
    WalkForwardOptimizer,
)


def _make_test_bars(count: int = 200) -> list[dict]:
    """Generate simple OHLCV bars for walk-forward testing."""
    bars = []
    for i in range(count):
        day = i + 1
        if day <= 31:
            ts = f"2024-01-{day:02d}"
        elif day <= 60:
            ts = f"2024-02-{(day - 31):02d}"
        elif day <= 91:
            ts = f"2024-03-{(day - 60):02d}"
        elif day <= 121:
            ts = f"2024-04-{(day - 91):02d}"
        elif day <= 152:
            ts = f"2024-05-{(day - 121):02d}"
        elif day <= 182:
            ts = f"2024-06-{(day - 152):02d}"
        elif day <= 213:
            ts = f"2024-07-{(day - 182):02d}"
        elif day <= 244:
            ts = f"2024-08-{(day - 213):02d}"
        elif day <= 274:
            ts = f"2024-09-{(day - 244):02d}"
        elif day <= 305:
            ts = f"2024-10-{(day - 274):02d}"
        elif day <= 335:
            ts = f"2024-11-{(day - 305):02d}"
        else:
            ts = f"2024-12-{(day - 335):02d}"
        close = 100.5 + i * 0.1
        bars.append(
            {
                "timestamp": ts,
                "open": 100.0 + i * 0.1,
                "high": 101.0 + i * 0.1,
                "low": 99.0 + i * 0.1,
                "close": close,
                "volume": 1000000,
                "sma_5": close,
                "sma_10": close,
            }
        )
    return bars


class _StubArtifactProvider:
    """Returns fixed bars."""

    def __init__(self, bars: list[dict]):
        self.bars = bars

    def get_artifact_bars(self, artifact_id: str) -> list[dict] | None:
        return self.bars[:]


class _StubParser:
    """Minimal parser that returns a simple SMA crossover definition."""

    class _ValidationResult:
        def __init__(self, valid=True, error=""):
            self.valid = valid
            self.error = error
            self.definition = None
            self.required_columns = []

    def parse(self, definition, params=None):
        result = self._ValidationResult()
        result.definition = _StubDefinition()
        result.required_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "sma_5",
            "sma_10",
        ]
        return result


class _StubStrategy:
    """A strategy that never trades (no signals)."""

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="stub",
            variant=DataMode.REAL,
            description="Stub strategy for testing",
            required_indicators=["sma_5", "sma_10"],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        return SignalResult(action="hold")

    def on_reset(self) -> None:
        pass

    @property
    def warmup_bars(self):
        return 0


class _StubDefinition:
    """Minimal strategy definition with no timeframes or features."""

    timeframes = None
    features = None
    warmup_bars = 0


class _StubFactory:
    """Creates a stub strategy from any definition."""

    def create(self, definition):
        return _StubStrategy()


@pytest.fixture
def walk_forward_setup():
    """Create a WalkForwardOptimizer with stubbed dependencies."""
    bars = _make_test_bars(200)
    provider = _StubArtifactProvider(bars)
    manager = InMemoryOptimizationJobManager()
    converter = PandasBarFrameConverter()

    config = OptimizerConfig(
        parser=_StubParser(),
        engine=BacktestRunner(),
        converter=converter,
        strategy_factory=_StubFactory(),
        manager=manager,
        artifact_provider=provider,
    )
    optimizer = WalkForwardOptimizer(config)
    return optimizer, manager, bars


class TestWalkForwardOptimizer:
    """Integration tests for the walk-forward optimizer."""

    @pytest.mark.asyncio
    async def test_run_completes_with_folds(self, walk_forward_setup):
        """A walk-forward job with valid bars completes and produces folds."""
        optimizer, manager, bars = walk_forward_setup

        job = OptimizationJob(
            job_id="wf-test-1",
            metric="sharpe_ratio",
            metadata={
                "definition": {},
                "bars_artifact_id": "test-artifact",
                "param_ranges": {
                    "fast_period": {"min": 5, "max": 20, "step": 5},
                },
                "wf_folds": 3,
                "wf_train_ratio": 0.7,
                "wf_anchor": "rolling",
                "initial_cash": 10000,
                "interval": "1d",
            },
        )

        await optimizer.run(job)
        assert job.status == "completed"
        wf_result = job.metadata.get("walk_forward_result")
        assert wf_result is not None
        assert wf_result.folds_completed >= 1

    @pytest.mark.asyncio
    async def test_too_few_bars_returns_no_folds(self, walk_forward_setup):
        """A walk-forward with too few bars completes with zero folds."""
        optimizer, manager, bars = walk_forward_setup
        provider = _StubArtifactProvider(_make_test_bars(5))
        optimizer._artifact_provider = provider

        job = OptimizationJob(
            job_id="wf-test-few",
            metric="sharpe_ratio",
            metadata={
                "definition": {},
                "bars_artifact_id": "test-artifact",
                "param_ranges": {"fast_period": {"min": 5, "max": 20, "step": 5}},
                "wf_folds": 3,
            },
        )

        await optimizer.run(job)
        assert job.status == "completed"
        wf_result = job.metadata.get("walk_forward_result")
        assert wf_result.folds_completed == 0

    @pytest.mark.asyncio
    async def test_produces_is_oos_correlation(self, walk_forward_setup):
        """Completed job includes OOS diagnostics."""
        optimizer, manager, bars = walk_forward_setup

        job = OptimizationJob(
            job_id="wf-diag",
            metric="sharpe_ratio",
            metadata={
                "definition": {},
                "bars_artifact_id": "test-artifact",
                "param_ranges": {
                    "fast_period": {"min": 5, "max": 20, "step": 5},
                },
                "wf_folds": 3,
                "interval": "1d",
            },
        )

        await optimizer.run(job)
        wf_result = job.metadata.get("walk_forward_result")
        assert wf_result is not None
        assert isinstance(wf_result.oos_sharpe, float)
        assert isinstance(wf_result.stability, float)
        assert isinstance(wf_result.is_oos_correlation, float)

    @pytest.mark.asyncio
    async def test_fold_indices_within_bounds(self):
        """Walk-forward fold indices respect bar count."""
        for total in [50, 100, 250, 500]:
            indices = compute_fold_indices(total, 5, 0.7, "rolling")
            if indices:
                for idx in indices:
                    assert idx["test_end"] <= total
                    assert idx["train_end"] <= total
                    assert idx["train_start"] >= 0
                    assert idx["test_start"] >= 0

    def test_anchored_folds_grow_training_window(self):
        """Anchored fold indices expand train window monotonically."""
        indices = compute_fold_indices(150, 5, 0.7, "anchored")
        train_ends = [i["train_end"] for i in indices]
        for i in range(len(train_ends) - 1):
            assert train_ends[i] <= train_ends[i + 1]
