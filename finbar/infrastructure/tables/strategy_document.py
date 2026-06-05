"""SQLAlchemy ORM table for v2 strategy documents."""

from sqlalchemy import Column, Integer, String, Text

from finbar.infrastructure.data.connection import Base


class StrategyDocument(Base):
    """Persisted v2 JSON strategy document."""

    __tablename__ = "strategy_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False, index=True)
    schema_version = Column(String, nullable=False, default="2.0")
    description = Column(String, default="")
    definition_json = Column(Text, nullable=False, default="{}")
    normalized_json = Column(Text, default="{}")
    tags_json = Column(Text, default="[]")
    created_at = Column(String, default="")
    updated_at = Column(String, default="")

    def __repr__(self) -> str:
        return (
            f"<StrategyDocument(name={self.name!r}, version={self.schema_version!r})>"
        )
