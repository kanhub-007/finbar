"""SQLite implementation of SymbolInfoRepository.

Repository pattern: all database access for symbol metadata goes here.
Implements the SymbolInfoRepository ABC from core/domain/interfaces/.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from finbar.core.domain.entities.symbol_info import (
    SymbolInfo as DomainSymbolInfo,
)
from finbar.core.domain.interfaces.symbol_info_repository import (
    SymbolInfoRepository,
)
from finbar.infrastructure.tables.symbol_info import (
    SymbolInfo as OrmSymbolInfo,
)

logger = logging.getLogger(__name__)


# ── Mapper functions ──────────────────────────────────────────────────────


def _domain_to_orm(info: DomainSymbolInfo) -> OrmSymbolInfo:
    """Convert domain SymbolInfo to ORM model."""
    return OrmSymbolInfo(
        symbol=info.symbol.upper(),
        company_name=info.company_name,
        sector=info.sector,
        industry=info.industry,
        exchange=info.exchange,
        market_cap=info.market_cap,
        fetched_at=info.fetched_at,
    )


def _orm_to_domain(orm: OrmSymbolInfo) -> DomainSymbolInfo:
    """Convert ORM model to domain SymbolInfo."""
    return DomainSymbolInfo(
        symbol=orm.symbol,
        company_name=orm.company_name or "",
        sector=orm.sector,
        industry=orm.industry,
        exchange=orm.exchange,
        market_cap=orm.market_cap,
        fetched_at=orm.fetched_at or "",
    )


# ── Repository ────────────────────────────────────────────────────────────


class SqlSymbolInfoRepository(SymbolInfoRepository):
    """SQLite-backed symbol metadata cache.

    Uses INSERT OR REPLACE for UPSERT semantics on symbol.
    """

    def __init__(self, db: Session):
        self._db = db

    def save(self, info: DomainSymbolInfo) -> None:
        """Save or update symbol metadata (UPSERT on symbol)."""
        try:
            orm_info = _domain_to_orm(info)
            stmt = (
                OrmSymbolInfo.__table__.insert()
                .prefix_with("OR REPLACE")
                .values(
                    symbol=orm_info.symbol,
                    company_name=orm_info.company_name,
                    sector=orm_info.sector,
                    industry=orm_info.industry,
                    exchange=orm_info.exchange,
                    market_cap=orm_info.market_cap,
                    fetched_at=orm_info.fetched_at,
                )
            )
            self._db.execute(stmt)
            self._db.commit()
        except Exception:
            logger.exception("Failed to save symbol info for %s", info.symbol)

    def find_by_symbol(self, symbol: str) -> DomainSymbolInfo | None:
        """Retrieve cached metadata for a symbol."""
        stmt = select(OrmSymbolInfo).where(OrmSymbolInfo.symbol == symbol.upper())
        result = self._db.execute(stmt).scalars().first()
        return _orm_to_domain(result) if result else None
