"""Tests for Phase 4 storage optimizations."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from finbar.core.domain.entities.indicator_job import IndicatorJob
from finbar.core.domain.services.content_hash import compute_artifact_hash
from finbar.infrastructure.data.connection import Base
from finbar.infrastructure.repositories.sql_backtest_result_repository import (
    SqlBacktestResultRepository,
)
from finbar.infrastructure.repositories.sql_indicator_artifact_repository import (
    SqlIndicatorArtifactRepository,
)
from finbar.infrastructure.services.in_memory_backtest_result_store import (
    InMemoryBacktestResultStore,
)
from finbar.infrastructure.services.in_memory_indicator_job_manager import (
    InMemoryIndicatorJobManager,
)
from finbar.infrastructure.tables.backtest_result import BacktestResult
from finbar.infrastructure.tables.indicator_artifact import (
    IndicatorArtifact,
)


@pytest.fixture
def db():
    """Create in-memory SQLite with backtest_results + indicator_artifacts tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[BacktestResult.__table__, IndicatorArtifact.__table__],
    )
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


def _sample_result() -> dict:
    return {
        "strategy_name": "test_strategy",
        "symbol": "AAPL",
        "interval": "1d",
        "start_date": "2024-01-01",
        "end_date": "2024-01-05",
        "bar_count": 100,
        "total_return": 0.15,
        "total_trades": 5,
        "trades": [{"entry_date": "2024-01-01", "net_pnl": 50, "duration_bars": 3}],
        "equity_curve": [{"date": "2024-01-01", "value": 10000, "drawdown": 0}],
    }


class TestBacktestResultPersistence:
    def test_save_and_load_from_sql(self, db):
        """Results persist to SQLite and survive restart."""
        store = InMemoryBacktestResultStore(session_factory=lambda: db)
        result_id = store.save(_sample_result())
        store2 = InMemoryBacktestResultStore(session_factory=lambda: db)

        loaded = store2.get(result_id)

        assert loaded is not None
        assert loaded["strategy_name"] == "test_strategy"

    def test_sql_list_results(self, db):
        """Listing discovers persisted results."""
        store = InMemoryBacktestResultStore(session_factory=lambda: db)
        store.save(_sample_result())
        repo = SqlBacktestResultRepository(db)
        results = repo.list_metadata(symbol="AAPL")
        assert len(results) >= 1
        assert results[0]["symbol"] == "AAPL"


class TestArtifactHashReuse:
    def test_hash_matches_for_same_inputs(self):
        """Identical inputs produce identical hashes."""
        args = dict(
            symbol="BTC-USD",
            source="yfinance",
            interval="5min",
            indicators=["sma_20", "rsi_14"],
            timeframe_alias="primary",
            start_date="2024-01-01",
            end_date="2024-06-01",
        )
        h1 = compute_artifact_hash(**args)
        h2 = compute_artifact_hash(**args)
        assert h1 == h2

    def test_hash_differs_for_different_intervals(self):
        """Different intervals produce different hashes."""
        base = dict(
            symbol="AAPL",
            source="yfinance",
            indicators=["sma_20"],
            timeframe_alias="primary",
            start_date=None,
            end_date=None,
        )
        assert compute_artifact_hash(**base, interval="1d") != compute_artifact_hash(
            **base, interval="1h"
        )

    def test_find_by_hash_returns_existing_artifact(self, db):
        """Stored artifacts with matching hash are discoverable."""
        repo = SqlIndicatorArtifactRepository(db)
        job = IndicatorJob(
            job_id="hash-test-1",
            symbol="AAPL",
            source="yfinance",
            interval="1d",
            timeframe_alias="primary",
            status="completed",
            indicators_applied=["sma_20"],
        )
        bars = [{"timestamp": "2024-01-01", "close": 100, "sma_20": 99}]
        content_hash = compute_artifact_hash(
            "AAPL", "yfinance", "1d", ["sma_20"], "primary", None, None
        )
        repo.save(job, bars, content_hash)

        found = repo.find_by_hash(content_hash)
        assert found == "hash-test-1"

        not_found = repo.find_by_hash("nonexistent-hash")
        assert not_found is None

    def test_manager_reuses_artifact_by_hash(self, db):
        """Completed artifacts are reused when the hash matches."""
        existing_hash = compute_artifact_hash(
            "AAPL", "yfinance", "1d", ["sma_20"], "primary", None, None
        )
        existing_job = IndicatorJob(
            job_id="reuse-existing-1",
            symbol="AAPL",
            source="yfinance",
            interval="1d",
            status="completed",
            indicators_applied=["sma_20"],
        )
        existing_bars = [{"timestamp": "2024-01-01", "close": 100, "sma_20": 99}]
        repo = SqlIndicatorArtifactRepository(db)
        repo.save(existing_job, existing_bars, existing_hash)

        manager = InMemoryIndicatorJobManager(session_factory=lambda: db)

        new_bars = manager.get_artifact_bars("reuse-existing-1")
        assert new_bars == existing_bars
