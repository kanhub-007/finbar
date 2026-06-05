"""SQLAlchemy ORM table for user-defined strategy definitions."""

import json

from sqlalchemy import Column, Integer, String, Text

from finbar.infrastructure.data.connection import Base


class StrategyDefinition(Base):
    """Persisted strategy definition — JSON-serialized rules."""

    __tablename__ = "strategy_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False, index=True)
    direction = Column(String, nullable=False, default="long")
    description = Column(String, default="")
    entry_rules_json = Column(Text, nullable=False, default="[]")
    exit_rules_json = Column(Text, nullable=False, default="[]")
    stop_loss_atr_mult = Column(String, default="0.0")
    take_profit_atr_mult = Column(String, default="0.0")
    require_all_entry_rules = Column(String, default="1")
    created_at = Column(String, default="")
    updated_at = Column(String, default="")

    def __repr__(self) -> str:
        return f"<StrategyDefinition(name={self.name!r})>"

    @staticmethod
    def domain_to_orm(domain: "StrategyDefinition") -> "StrategyDefinition":
        """Convert a domain StrategyDefinition entity to ORM row."""

        orm = StrategyDefinition()
        orm.name = domain.name
        orm.direction = domain.direction
        orm.description = domain.description
        orm.entry_rules_json = json.dumps(
            [
                {"indicator": r.indicator, "operator": r.operator, "value": r.value}
                for r in domain.entry_rules
            ]
        )
        orm.exit_rules_json = json.dumps(
            [
                {"indicator": r.indicator, "operator": r.operator, "value": r.value}
                for r in domain.exit_rules
            ]
        )
        orm.stop_loss_atr_mult = str(domain.stop_loss_atr_mult)
        orm.take_profit_atr_mult = str(domain.take_profit_atr_mult)
        orm.require_all_entry_rules = "1" if domain.require_all_entry_rules else "0"
        orm.created_at = domain.created_at
        orm.updated_at = domain.updated_at
        return orm

    @staticmethod
    def orm_to_domain(orm: "StrategyDefinition") -> "StrategyDefinition":
        """Convert an ORM row to a domain StrategyDefinition entity."""
        from finbar.core.domain.entities.rule import Rule
        from finbar.core.domain.entities.strategy_definition import (
            StrategyDefinition as DomainDef,
        )

        entry_raw = json.loads(orm.entry_rules_json or "[]")
        exit_raw = json.loads(orm.exit_rules_json or "[]")

        return DomainDef(
            name=orm.name,
            direction=orm.direction,
            description=orm.description or "",
            entry_rules=[
                Rule(
                    indicator=r["indicator"],
                    operator=r["operator"],
                    value=r["value"],
                )
                for r in entry_raw
            ],
            exit_rules=[
                Rule(
                    indicator=r["indicator"],
                    operator=r["operator"],
                    value=r["value"],
                )
                for r in exit_raw
            ],
            stop_loss_atr_mult=float(orm.stop_loss_atr_mult or "0"),
            take_profit_atr_mult=float(orm.take_profit_atr_mult or "0"),
            require_all_entry_rules=orm.require_all_entry_rules == "1",
            created_at=orm.created_at or "",
            updated_at=orm.updated_at or "",
        )
