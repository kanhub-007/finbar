"""Observability tests for the indicator job runner — spec 2026-06-16 Scenario 4.

Verifies that handler failures surfaced by the calculator (via
``df.attrs[FAILED_INDICATORS_ATTR]``) propagate all the way to job
progress, so users and the LLM see which metrics failed and why instead
of silent NaN columns.

Classical school: real ``PandasTaIndicatorCalculator`` with a real
crashing handler injected into the live registry, real
``InMemoryIndicatorJobManager``, real converter. No mocks. Asserts on
the outcome (job state + progress DTO).
"""

import numpy as np
import pandas as pd
import pytest
from finbar_strategy_runtime.indicators._handler_registry import (
    _INDICATOR_HANDLERS,
)
from finbar_strategy_runtime.indicators.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)

from finbar.core.application.use_cases.get_indicator_job_progress import (
    GetIndicatorJobProgressUseCase,
)
from finbar.core.domain.entities.indicator_job import IndicatorJob
from finbar.infrastructure.services.in_memory_indicator_job_manager import (
    InMemoryIndicatorJobManager,
)
from finbar.infrastructure.services.indicator_job_runner import (
    CachedPriceIndicatorJobRunner,
)


def _bars(n: int = 30) -> list[dict]:
    """Build n OHLCV bar dicts (enough for sma_20 warmup)."""
    close = np.linspace(100.0, 130.0, n)
    ts = pd.date_range("2026-01-01", periods=n, freq="D")
    return [
        {
            "timestamp": ts[i].isoformat(),
            "open": float(close[i]),
            "high": float(close[i] + 1.0),
            "low": float(close[i] - 1.0),
            "close": float(close[i]),
            "volume": 1_000_000.0,
        }
        for i in range(n)
    ]


@pytest.fixture
def crashing_handler():
    """Register a handler that always raises (mirrors the volume-arg bug)."""
    name = "__test_runner_crash__"

    def _handler(df, _n, _cache):
        raise TypeError("missing required positional argument 'volume'")

    _INDICATOR_HANDLERS[name] = (_handler, set())
    try:
        yield name
    finally:
        _INDICATOR_HANDLERS.pop(name, None)


def _make_runner(manager: InMemoryIndicatorJobManager) -> CachedPriceIndicatorJobRunner:
    """Build a real runner. session_factory is unused by _apply_indicators."""
    return CachedPriceIndicatorJobRunner(
        session_factory=None,
        manager=manager,
        indicator_calculator=PandasTaIndicatorCalculator(),
        converter=PandasBarFrameConverter(),
        feature_calculator=None,
        parser=None,
    )


class TestRunnerSurfacesFailedIndicators:
    """Scenario 4 — failures propagate calculator -> job -> progress DTO."""

    def test_apply_indicators_records_failures_on_job(self, crashing_handler):
        """A crashing handler is recorded on the job's failed_indicators."""
        manager = InMemoryIndicatorJobManager()
        runner = _make_runner(manager)
        job = IndicatorJob(
            job_id="job-1",
            symbol="AAPL",
            interval="1d",
            mode="selected",
        )
        manager._jobs[job.job_id] = job

        runner._apply_indicators(job, _bars(), ["sma_20", crashing_handler])

        assert any(
            name == crashing_handler for name, _ in job.failed_indicators
        )
        crash = next(
            err for name, err in job.failed_indicators if name == crashing_handler
        )
        assert "volume" in crash

    def test_progress_use_case_surfaces_failed_indicators(self, crashing_handler):
        """get_indicator_job_progress surfaces failed_indicators directly."""
        manager = InMemoryIndicatorJobManager()
        runner = _make_runner(manager)
        job = IndicatorJob(
            job_id="job-2",
            symbol="AAPL",
            interval="1d",
            mode="selected",
        )
        manager._jobs[job.job_id] = job

        runner._apply_indicators(job, _bars(), ["sma_20", crashing_handler])

        progress = GetIndicatorJobProgressUseCase(manager).execute(job.job_id)

        assert progress.found is True
        assert any(
            name == crashing_handler for name, _ in progress.failed_indicators
        )

    def test_clean_run_has_empty_failed_indicators(self):
        """A run with no crashes reports an empty failed_indicators list."""
        manager = InMemoryIndicatorJobManager()
        runner = _make_runner(manager)
        job = IndicatorJob(
            job_id="job-3",
            symbol="AAPL",
            interval="1d",
            mode="selected",
        )
        manager._jobs[job.job_id] = job

        runner._apply_indicators(job, _bars(), ["sma_20"])

        assert job.failed_indicators == []
