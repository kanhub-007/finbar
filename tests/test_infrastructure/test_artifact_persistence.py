"""Tests for SQLite-backed enrichment artifact persistence."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
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

        deleted = repo.delete("del-1")

        assert deleted is True
        assert repo.get_bars("del-1") is None

    def test_cleanup_expired_honors_ttl_hours(self, mem_db):
        """Cleanup removes only artifacts older than the requested TTL."""

        repo = SqlIndicatorArtifactRepository(mem_db)
        fresh = IndicatorJob(job_id="fresh-1", symbol="AAPL")
        old = IndicatorJob(job_id="old-1", symbol="AAPL")
        repo.save(fresh, [{"timestamp": "2024-01-02", "close": 101}])
        repo.save(old, [{"timestamp": "2024-01-01", "close": 100}])

        old_row = mem_db.execute(
            select(OrmArtifact).where(OrmArtifact.job_id == "old-1")
        ).scalar_one()
        old_row.created_at = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
        mem_db.commit()

        deleted_count = repo.cleanup_expired(ttl_hours=24)

        assert deleted_count == 1
        assert repo.get_bars("old-1") is None
        assert repo.get_bars("fresh-1") is not None

    def test_describe_and_query_artifact_bars(self, mem_db):
        """Artifacts expose metadata and selective paginated bar access."""

        repo = SqlIndicatorArtifactRepository(mem_db)
        job = IndicatorJob(
            job_id="query-1",
            symbol="BTC-USD",
            source="yfinance",
            interval="5min",
            indicators_applied=["sma_20"],
        )
        bars = [
            {"timestamp": "2024-01-01", "close": 100, "sma_20": None},
            {"timestamp": "2024-01-02", "close": 101, "sma_20": 100.5},
            {"timestamp": "2024-01-03", "close": 102, "sma_20": 101.0},
        ]
        repo.save(job, bars)

        metadata = repo.describe("query-1")
        result = repo.query_bars(
            "query-1",
            columns=["timestamp", "sma_20"],
            start_date="2024-01-02",
            page=0,
            page_size=1,
        )

        page_bars, page, page_size, total_pages, total, columns = result
        assert metadata["artifact_id"] == "query-1"
        assert metadata["retention_policy"] == "durable_until_deleted"
        assert metadata["null_counts"]["sma_20"] == 1
        assert page_bars == [{"timestamp": "2024-01-02", "sma_20": 100.5}]
        assert (page, page_size, total_pages, total) == (0, 1, 2, 2)
        assert columns == ["timestamp", "sma_20"]


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

    def test_cleanup_expired_keeps_persisted_artifacts(self, mem_db):
        """In-memory TTL cleanup evicts hot cache but keeps durable SQLite data."""

        manager = InMemoryIndicatorJobManager(
            ttl_seconds=1,
            session_factory=lambda: mem_db,
        )
        job = IndicatorJob(
            job_id="durable-1",
            symbol="AAPL",
            status="completed",
            created_at=datetime.now(UTC) - timedelta(seconds=5),
        )
        bars = [{"timestamp": "2024-01-01", "close": 100}]
        manager.store_result(job, bars)

        manager.cleanup_expired()

        assert manager.get_artifact_bars("durable-1") == bars

    def test_query_artifact_bars_falls_back_to_sql_after_restart(self, mem_db):
        """Artifact query works through the manager after in-memory restart."""

        manager = InMemoryIndicatorJobManager(session_factory=lambda: mem_db)
        job = IndicatorJob(job_id="page-1", symbol="AAPL", status="completed")
        manager.store_result(
            job,
            [
                {"timestamp": "2024-01-01", "close": 100, "rsi_14": 40},
                {"timestamp": "2024-01-02", "close": 101, "rsi_14": 45},
            ],
        )
        manager2 = InMemoryIndicatorJobManager(session_factory=lambda: mem_db)

        bars, page, page_size, total_pages, total, columns = (
            manager2.query_artifact_bars(
                "page-1",
                columns=["timestamp", "rsi_14"],
                page=0,
                page_size=10,
            )
        )

        assert bars == [
            {"timestamp": "2024-01-01", "rsi_14": 40},
            {"timestamp": "2024-01-02", "rsi_14": 45},
        ]
        assert (page, page_size, total_pages, total) == (0, 10, 1, 2)
        assert columns == ["timestamp", "rsi_14"]
