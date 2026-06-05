"""SQLite repository for strategy documents."""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from finbar.core.domain.entities.strategy_document import StrategyDocument
from finbar.core.domain.interfaces.strategy_document_repository import (
    StrategyDocumentRepository,
)
from finbar.infrastructure.tables.strategy_document import (
    StrategyDocument as OrmStrategyDocument,
)

logger = logging.getLogger(__name__)


class SqlStrategyDocumentRepository(StrategyDocumentRepository):
    """SQLite-backed CRUD for strategy documents."""

    def __init__(self, db: Session):
        """Constructor injection — receives a database session.

        Args:
            db: SQLAlchemy session. Caller manages lifecycle.
        """
        self._db = db

    def save(self, document: StrategyDocument) -> None:
        """Insert or update a strategy document."""
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")

        existing = (
            self._db.query(OrmStrategyDocument)
            .filter(OrmStrategyDocument.name == document.name)
            .first()
        )

        if existing:
            existing.schema_version = document.schema_version
            existing.description = document.description
            existing.definition_json = document.definition_json
            existing.normalized_json = document.normalized_json
            existing.tags_json = json.dumps(document.tags)
            existing.updated_at = now
            logger.info("Updated strategy document '%s'", document.name)
        else:
            orm = _domain_to_orm(document)
            orm.created_at = now
            orm.updated_at = now
            self._db.add(orm)
            logger.info("Created strategy document '%s'", document.name)

        self._db.commit()

    def find_by_name(self, name: str) -> StrategyDocument | None:
        """Retrieve a strategy document by name."""
        orm = (
            self._db.query(OrmStrategyDocument)
            .filter(OrmStrategyDocument.name == name)
            .first()
        )
        if orm is None:
            return None
        return _orm_to_domain(orm)

    def list_all(self) -> list[StrategyDocument]:
        """List all strategy documents."""
        orms = (
            self._db.query(OrmStrategyDocument).order_by(OrmStrategyDocument.name).all()
        )
        return [_orm_to_domain(o) for o in orms]

    def delete(self, name: str) -> bool:
        """Delete a strategy document by name."""
        orm = (
            self._db.query(OrmStrategyDocument)
            .filter(OrmStrategyDocument.name == name)
            .first()
        )
        if orm is None:
            return False
        self._db.delete(orm)
        self._db.commit()
        logger.info("Deleted strategy document '%s'", name)
        return True


def _domain_to_orm(document: StrategyDocument) -> OrmStrategyDocument:
    orm = OrmStrategyDocument()
    orm.name = document.name
    orm.schema_version = document.schema_version
    orm.description = document.description
    orm.definition_json = document.definition_json
    orm.normalized_json = document.normalized_json
    orm.tags_json = json.dumps(document.tags)
    return orm


def _orm_to_domain(orm: OrmStrategyDocument) -> StrategyDocument:
    return StrategyDocument(
        id=orm.id,
        name=orm.name,
        schema_version=orm.schema_version,
        description=orm.description or "",
        definition_json=orm.definition_json or "{}",
        normalized_json=orm.normalized_json or "{}",
        tags=json.loads(orm.tags_json or "[]"),
        created_at=orm.created_at or "",
        updated_at=orm.updated_at or "",
    )
