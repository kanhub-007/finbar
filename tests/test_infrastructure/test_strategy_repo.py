"""Integration tests for strategy definition CRUD with in-memory SQLite."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from finbar.core.domain.entities.rule import Rule
from finbar.core.domain.entities.strategy_definition import StrategyDefinition
from finbar.infrastructure.data.connection import Base
from finbar.infrastructure.repositories.sql_strategy_definition_repository import (
    SqlStrategyDefinitionRepository,
)
from finbar.infrastructure.tables.strategy_definition import (
    StrategyDefinition as OrmStrategyDef,
)


@pytest.fixture
def db():
    """Create an in-memory SQLite database with strategy_definitions table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[OrmStrategyDef.__table__])
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def repo(db):
    return SqlStrategyDefinitionRepository(db)


class TestSaveAndRetrieve:
    def test_save_new_strategy(self, repo, db):
        sdef = StrategyDefinition(
            name="test_strategy",
            direction="long",
            description="A test strategy",
            entry_rules=[
                Rule(indicator="rsi_14", operator="<", value=30),
            ],
            exit_rules=[
                Rule(indicator="rsi_14", operator=">", value=70),
            ],
            stop_loss_atr_mult=2.0,
            take_profit_atr_mult=3.0,
        )
        repo.save(sdef)
        retrieved = repo.find_by_name("test_strategy")
        assert retrieved is not None
        assert retrieved.name == "test_strategy"
        assert retrieved.direction == "long"
        assert len(retrieved.entry_rules) == 1
        assert len(retrieved.exit_rules) == 1
        assert retrieved.stop_loss_atr_mult == 2.0
        assert retrieved.take_profit_atr_mult == 3.0
        assert retrieved.created_at != ""

    def test_update_existing_strategy(self, repo, db):
        sdef = StrategyDefinition(
            name="update_test",
            direction="long",
            entry_rules=[Rule(indicator="rsi_14", operator="<", value=30)],
            exit_rules=[],
        )
        repo.save(sdef)

        # Update
        updated = StrategyDefinition(
            name="update_test",
            direction="short",
            entry_rules=[Rule(indicator="rsi_14", operator=">", value=70)],
            exit_rules=[],
        )
        repo.save(updated)

        retrieved = repo.find_by_name("update_test")
        assert retrieved.direction == "short"
        assert retrieved.entry_rules[0].operator == ">"
        # updated_at should be set
        assert retrieved.updated_at != ""

    def test_find_by_name_not_found(self, repo):
        assert repo.find_by_name("nonexistent") is None


class TestListAll:
    def test_list_empty(self, repo):
        assert repo.list_all() == []

    def test_list_sorted(self, repo):
        repo.save(StrategyDefinition(name="z_strategy", direction="long"))
        repo.save(StrategyDefinition(name="a_strategy", direction="short"))
        all_defs = repo.list_all()
        assert len(all_defs) == 2
        assert all_defs[0].name == "a_strategy"

    def test_list_excludes_deleted(self, repo):
        repo.save(StrategyDefinition(name="temp", direction="long"))
        repo.delete("temp")
        assert repo.list_all() == []


class TestDelete:
    def test_delete_existing(self, repo):
        repo.save(StrategyDefinition(name="delete_me", direction="long"))
        assert repo.delete("delete_me") is True
        assert repo.find_by_name("delete_me") is None

    def test_delete_nonexistent(self, repo):
        assert repo.delete("nonexistent") is False

    def test_delete_then_recreate(self, repo):
        repo.save(StrategyDefinition(name="recreate", direction="long"))
        repo.delete("recreate")
        repo.save(StrategyDefinition(name="recreate", direction="short"))
        retrieved = repo.find_by_name("recreate")
        assert retrieved.direction == "short"


class TestRuleRoundtrip:
    def test_complex_rules_preserved(self, repo, db):
        sdef = StrategyDefinition(
            name="complex",
            direction="both",
            entry_rules=[
                Rule(indicator="rsi_14", operator="<", value=30),
                Rule(indicator="close", operator=">", value="sma_50"),
                Rule(indicator="rvol", operator=">", value=1.5),
            ],
            exit_rules=[
                Rule(indicator="rsi_14", operator=">", value=70),
                Rule(indicator="close", operator="crosses_below", value="sma_20"),
            ],
            stop_loss_atr_mult=2.5,
            take_profit_atr_mult=4.0,
            require_all_entry_rules=False,
        )
        repo.save(sdef)
        retrieved = repo.find_by_name("complex")
        assert len(retrieved.entry_rules) == 3
        assert retrieved.entry_rules[1].indicator == "close"
        assert retrieved.entry_rules[1].value == "sma_50"
        assert retrieved.exit_rules[1].operator == "crosses_below"
        assert retrieved.require_all_entry_rules is False


class TestORMConversion:
    def test_domain_to_orm_roundtrip(self):
        original = StrategyDefinition(
            name="roundtrip",
            direction="long",
            description="Test roundtrip",
            entry_rules=[Rule(indicator="rsi_14", operator="<", value=30)],
            exit_rules=[Rule(indicator="rsi_14", operator=">", value=70)],
            stop_loss_atr_mult=1.5,
            take_profit_atr_mult=2.0,
            require_all_entry_rules=True,
        )
        orm = OrmStrategyDef.domain_to_orm(original)
        restored = OrmStrategyDef.orm_to_domain(orm)
        assert restored.name == original.name
        assert restored.direction == original.direction
        assert len(restored.entry_rules) == len(original.entry_rules)
        assert restored.stop_loss_atr_mult == original.stop_loss_atr_mult

    def test_orm_to_domain_handles_empty_json(self):
        orm = OrmStrategyDef(
            name="empty_test",
            direction="long",
            entry_rules_json="[]",
            exit_rules_json="[]",
        )
        domain = OrmStrategyDef.orm_to_domain(orm)
        assert domain.entry_rules == []
        assert domain.exit_rules == []
