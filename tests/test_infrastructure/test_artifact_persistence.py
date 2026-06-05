"""Tests for SQLite-backed enrichment artifact persistence."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from finbar.core.domain.entities.indicator_job import IndicatorJob
from finbar.infrastructure.data.connection import Base
from finbar.infrastructure.repositories.sql_indicator_artifact_repository import (
    SqlIndicatorArtifactRepository,
)
from finbar.infrastructure.services.in_memory_indicator_job_manager import (
    InMemoryIndicatorJobManager,
)
from finbar.infrastructure.tables.indicator_artifact import (
    IndicatorArtifact as OrmArtifact,
)


@pytest.fixture
def mem_db():
    """Create an in-memory SQLite database with indicator_artifacts table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[OrmArtifact.__table__])
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


class TestSqlIndicatorArtifactRepository:
    def test_save_and_retrieve_bars(self, mem_db):
        """Artifacts saved to SQLite are retrievable."""

        repo = SqlIndicatorArtifactRepository(mem_db)
        job = IndicatorJob(
            job_id="test-123", symbol="AAPL", source="yfinance", interval="1d"
        )
        bars = [{"timestamp": "2024-01-01", "close": 100}]

        repo.save(job, bars)
        result = repo.get_bars("test-123")

        assert result == bars

    def test_get_metadata_reconstructs_job(self, mem_db):
        """Minimal job metadata is reconstructed from SQLite."""

        repo = SqlIndicatorArtifactRepository(mem_db)
        job = IndicatorJob(
            job_id="test-456",
            symbol="TSLA",
            source="hyperliquid",
            interval="1h",
            mode="strategy_required",
            timeframe_alias="primary",
            indicators_applied=["sma_20"],
        )
        repo.save(job, [])

        result = repo.get_metadata("test-456")

        assert result is not None
        assert result.job_id == "test-456"
        assert result.symbol == "TSLA"
        assert result.indicators_applied == ["sma_20"]

    def test_missing_returns_none(self, mem_db):
        """Missing artifacts return None for both bars and metadata."""

        repo = SqlIndicatorArtifactRepository(mem_db)

        assert repo.get_bars("missing") is None
        assert repo.get_metadata("missing") is None

    def test_delete_removes_artifact(self, mem_db):
        """Deleted artifacts are no longer retrievable."""

        repo = SqlIndicatorArtifactRepository(mem_db)
        job = IndicatorJob(job_id="del-1", symbol="AAPL")
        repo.save(job, [{"close": 100}])

        repo.delete("del-1")

        assert repo.get_bars("del-1") is None


class TestManagerSqlFallback:
    def test_artifact_bars_fallback_to_sql_on_restart(self, mem_db):
        """After a simulated restart (empty in-memory), SQLite fallback works."""

        manager = InMemoryIndicatorJobManager(session_factory=lambda: mem_db)
        job = IndicatorJob(job_id="restart-1", symbol="AAPL")
        bars = [{"timestamp": "2024-01-01", "close": 100}]
        manager.update(job, status="completed")
        manager.store_result(job, bars)

        # Simulate restart: new manager instance with same SQLite
        manager2 = InMemoryIndicatorJobManager(session_factory=lambda: mem_db)

        result = manager2.get_artifact_bars("restart-1")

        assert result == bars

    def test_artifact_job_fallback_to_sql_on_restart(self, mem_db):
        """Metadata is retrieved from SQLite after simulated restart."""

        manager = InMemoryIndicatorJobManager(session_factory=lambda: mem_db)
        job = IndicatorJob(
            job_id="meta-1",
            symbol="AAPL",
            mode="strategy_required",
        )
        manager.update(job, status="completed")
        manager.store_result(job, [])

        manager2 = InMemoryIndicatorJobManager(session_factory=lambda: mem_db)

        result = manager2.get_artifact_job("meta-1")

        assert result is not None
        assert result.job_id == "meta-1"
        assert result.status == "completed"
