"""SQLite repository for user-defined strategy definitions."""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from finbar.core.domain.entities.strategy_definition import StrategyDefinition
from finbar.core.domain.interfaces.strategy_definition_repository import (
    StrategyDefinitionRepository,
)
from finbar.infrastructure.tables.strategy_definition import (
    StrategyDefinition as OrmStrategyDef,
)

logger = logging.getLogger(__name__)


class SqlStrategyDefinitionRepository(StrategyDefinitionRepository):
    """SQLite-backed CRUD for user-defined strategy definitions."""

    def __init__(self, db: Session):
        """Constructor injection — receives a database session.

        Args:
            db: SQLAlchemy session. Caller manages lifecycle.
        """
        self._db = db

    def save(self, definition: StrategyDefinition) -> None:
        """Insert or update a strategy definition."""
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")

        existing = (
            self._db.query(OrmStrategyDef)
            .filter(OrmStrategyDef.name == definition.name)
            .first()
        )

        if existing:
            # Update
            existing.direction = definition.direction
            existing.description = definition.description
            existing.entry_rules_json = _rules_to_json(definition.entry_rules)
            existing.exit_rules_json = _rules_to_json(definition.exit_rules)
            existing.stop_loss_atr_mult = str(definition.stop_loss_atr_mult)
            existing.take_profit_atr_mult = str(definition.take_profit_atr_mult)
            existing.require_all_entry_rules = (
                "1" if definition.require_all_entry_rules else "0"
            )
            existing.updated_at = now
            logger.info("Updated strategy definition '%s'", definition.name)
        else:
            # Insert
            orm = OrmStrategyDef.domain_to_orm(definition)
            orm.created_at = now
            orm.updated_at = now
            self._db.add(orm)
            logger.info("Created strategy definition '%s'", definition.name)

        self._db.commit()

    def find_by_name(self, name: str) -> StrategyDefinition | None:
        """Retrieve a strategy definition by name."""
        orm = self._db.query(OrmStrategyDef).filter(OrmStrategyDef.name == name).first()
        if orm is None:
            return None
        return OrmStrategyDef.orm_to_domain(orm)

    def list_all(self) -> list[StrategyDefinition]:
        """List all user-defined strategy definitions."""
        orms = self._db.query(OrmStrategyDef).order_by(OrmStrategyDef.name).all()
        return [OrmStrategyDef.orm_to_domain(o) for o in orms]

    def delete(self, name: str) -> bool:
        """Delete a strategy definition by name."""
        orm = self._db.query(OrmStrategyDef).filter(OrmStrategyDef.name == name).first()
        if orm is None:
            return False
        self._db.delete(orm)
        self._db.commit()
        logger.info("Deleted strategy definition '%s'", name)
        return True


def _rules_to_json(rules: list) -> str:
    """Serialize a list of Rule objects to JSON string."""
    import json

    return json.dumps(
        [
            {"indicator": r.indicator, "operator": r.operator, "value": r.value}
            for r in rules
        ]
    )
