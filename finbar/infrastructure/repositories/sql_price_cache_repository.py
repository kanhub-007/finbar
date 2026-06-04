"""SQLite implementation of PriceCacheRepository.

Repository pattern: all database access for OHLCV bars goes through this class.
Implements the PriceCacheRepository ABC from core/domain/interfaces/.

UPSERT pattern adapted from h_stocks postgres_price_repository save_bars()
(replaced PostgreSQL INSERT ON CONFLICT with SQLite INSERT OR REPLACE).
"""

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from finbar.core.domain.entities.price_bar import PriceBar as DomainPriceBar
from finbar.core.domain.interfaces.price_cache_repository import (
    PriceCacheRepository,
)
from finbar.infrastructure.tables.price_bar import (
    PriceBar as OrmPriceBar,
)

logger = logging.getLogger(__name__)


# ── Mapper functions (Domain ↔ ORM) ──────────────────────────────────────


def _domain_to_orm(bar: DomainPriceBar) -> OrmPriceBar:
    """Convert domain PriceBar to ORM model."""
    return OrmPriceBar(
        symbol=bar.symbol.upper(),
        source=bar.source,
        interval=bar.interval,
        timestamp=bar.timestamp,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
    )


def _orm_to_domain(orm: OrmPriceBar) -> DomainPriceBar:
    """Convert ORM model to domain PriceBar."""
    return DomainPriceBar(
        symbol=orm.symbol,
        source=orm.source,
        interval=orm.interval,
        timestamp=orm.timestamp,
        open=orm.open,
        high=orm.high,
        low=orm.low,
        close=orm.close,
        volume=orm.volume,
    )


# ── Repository ────────────────────────────────────────────────────────────


class SqlPriceCacheRepository(PriceCacheRepository):
    """SQLite-backed price bar cache.

    Uses INSERT OR REPLACE for UPSERT semantics — bars with the same
    (symbol, source, interval, timestamp) are replaced rather than duplicated.
    """

    def __init__(self, db: Session):
        self._db = db

    def save_bars(self, bars: list[DomainPriceBar]) -> int:
        """Save price bars with UPSERT semantics.

        Uses SQLite's INSERT OR REPLACE which deletes the old row and inserts
        a new one when a UNIQUE constraint violation occurs.

        Note: currently loops one-by-one. For large batches (1000+ bars),
        a bulk INSERT OR REPLACE with executemany can be added later.

        Args:
            bars: List of PriceBar domain entities.

        Returns:
            Number of bars saved.
        """
        if not bars:
            return 0

        count = 0
        for bar in bars:
            try:
                orm_bar = _domain_to_orm(bar)
                # INSERT OR REPLACE: on unique constraint violation,
                # delete old row and insert new
                stmt = (
                    OrmPriceBar.__table__.insert()
                    .prefix_with("OR REPLACE")
                    .values(
                        symbol=orm_bar.symbol,
                        source=orm_bar.source,
                        interval=orm_bar.interval,
                        timestamp=orm_bar.timestamp,
                        open=orm_bar.open,
                        high=orm_bar.high,
                        low=orm_bar.low,
                        close=orm_bar.close,
                        volume=orm_bar.volume,
                    )
                )
                self._db.execute(stmt)
                count += 1
            except Exception:
                logger.exception(
                    "Failed to save bar for %s at %s",
                    bar.symbol,
                    bar.timestamp,
                )

        self._db.commit()
        return count

    def query_bars(
        self,
        symbol: str,
        source: str,
        interval: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[DomainPriceBar]:
        """Retrieve cached bars, ordered by timestamp ascending."""
        stmt = select(OrmPriceBar).where(
            OrmPriceBar.symbol == symbol.upper(),
            OrmPriceBar.source == source,
            OrmPriceBar.interval == interval,
        )

        if start_date:
            stmt = stmt.where(OrmPriceBar.timestamp >= start_date)
        if end_date:
            stmt = stmt.where(OrmPriceBar.timestamp <= end_date)

        stmt = stmt.order_by(OrmPriceBar.timestamp.asc())

        result = self._db.execute(stmt).scalars().all()
        return [_orm_to_domain(row) for row in result]

    def delete_bars(
        self,
        symbol: str,
        source: str | None = None,
        interval: str | None = None,
        before_date: str | None = None,
    ) -> int:
        """Delete bars. Symbol is required; other params narrow scope."""
        stmt = delete(OrmPriceBar).where(OrmPriceBar.symbol == symbol.upper())

        if source:
            stmt = stmt.where(OrmPriceBar.source == source)
        if interval:
            stmt = stmt.where(OrmPriceBar.interval == interval)
        if before_date:
            stmt = stmt.where(OrmPriceBar.timestamp < before_date)

        result = self._db.execute(stmt)
        self._db.commit()
        return result.rowcount

    def list_symbols(self, source: str | None = None) -> list[str]:
        """Return sorted distinct symbols in cache."""
        stmt = select(OrmPriceBar.symbol).distinct()
        if source:
            stmt = stmt.where(OrmPriceBar.source == source)
        stmt = stmt.order_by(OrmPriceBar.symbol.asc())

        result = self._db.execute(stmt).scalars().all()
        return list(result)

    def get_latest_bar(
        self,
        symbol: str,
        source: str,
        interval: str,
    ) -> DomainPriceBar | None:
        """Get the most recent bar."""
        stmt = (
            select(OrmPriceBar)
            .where(
                OrmPriceBar.symbol == symbol.upper(),
                OrmPriceBar.source == source,
                OrmPriceBar.interval == interval,
            )
            .order_by(OrmPriceBar.timestamp.desc())
            .limit(1)
        )

        result = self._db.execute(stmt).scalars().first()
        return _orm_to_domain(result) if result else None
