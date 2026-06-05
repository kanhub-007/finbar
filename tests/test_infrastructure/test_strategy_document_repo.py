"""Integration tests for v2 strategy document CRUD with in-memory SQLite."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from finbar.core.domain.entities.strategy_document import StrategyDocument
from finbar.infrastructure.data.connection import Base
from finbar.infrastructure.repositories.sql_strategy_document_repository import (
    SqlStrategyDocumentRepository,
)
from finbar.infrastructure.tables.strategy_document import (
    StrategyDocument as OrmStrategyDoc,
)


@pytest.fixture
def db():
    """Create an in-memory SQLite database with strategy_documents table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[OrmStrategyDoc.__table__])
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def repo(db):
    return SqlStrategyDocumentRepository(db)


_SMA_JSON = json.dumps(
    {
        "schema_version": "2.0",
        "name": "saved_sma_cross",
        "indicators": [
            {"name": "fast_sma", "type": "sma", "period": "{{ fast_period }}"},
            {"name": "slow_sma", "type": "sma", "period": "{{ slow_period }}"},
        ],
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {
                                "left": "fast_sma",
                                "operator": "crosses_above",
                                "right": "slow_sma",
                            }
                        ]
                    }
                }
            }
        },
    }
)


class TestSaveAndRetrieve:
    def test_save_new_document(self, repo, db):
        doc = StrategyDocument(
            name="sma_cross_v2",
            schema_version="2.0",
            definition_json=_SMA_JSON,
            description="Saved SMA crossover",
        )
        repo.save(doc)
        retrieved = repo.find_by_name("sma_cross_v2")
        assert retrieved is not None
        assert retrieved.name == "sma_cross_v2"
        assert retrieved.schema_version == "2.0"
        assert retrieved.description == "Saved SMA crossover"
        assert retrieved.definition_json == _SMA_JSON

    def test_update_existing_document(self, repo, db):
        doc = StrategyDocument(
            name="sma_cross_v2",
            schema_version="2.0",
            definition_json=_SMA_JSON,
            description="v1",
        )
        repo.save(doc)

        updated = StrategyDocument(
            name="sma_cross_v2",
            schema_version="2.0",
            definition_json=_SMA_JSON,
            description="v2 updated",
        )
        repo.save(updated)

        retrieved = repo.find_by_name("sma_cross_v2")
        assert retrieved is not None
        assert retrieved.description == "v2 updated"

    def test_find_nonexistent_returns_none(self, repo):
        assert repo.find_by_name("no_such_strategy") is None

    def test_list_all(self, repo, db):
        repo.save(
            StrategyDocument(
                name="alpha", schema_version="2.0", definition_json=_SMA_JSON
            )
        )
        repo.save(
            StrategyDocument(
                name="beta", schema_version="2.0", definition_json=_SMA_JSON
            )
        )
        all_docs = repo.list_all()
        assert len(all_docs) == 2
        assert all_docs[0].name == "alpha"
        assert all_docs[1].name == "beta"

    def test_delete_existing(self, repo, db):
        repo.save(
            StrategyDocument(
                name="to_delete", schema_version="2.0", definition_json=_SMA_JSON
            )
        )
        assert repo.delete("to_delete") is True
        assert repo.find_by_name("to_delete") is None

    def test_delete_nonexistent(self, repo):
        assert repo.delete("no_such") is False

    def test_update_preserves_created_at_but_updates_updated_at(self, repo, db):
        doc = StrategyDocument(
            name="timed_strategy",
            schema_version="2.0",
            definition_json=_SMA_JSON,
        )
        repo.save(doc)
        first = repo.find_by_name("timed_strategy")
        assert first is not None
        created = first.created_at
        assert created != ""

        repo.save(
            StrategyDocument(
                name="timed_strategy",
                schema_version="2.0",
                definition_json=_SMA_JSON,
                description="modified",
            )
        )
        second = repo.find_by_name("timed_strategy")
        assert second is not None
        assert second.created_at == created
        assert second.updated_at >= created
