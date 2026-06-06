"""SqlCoinGlassRepository — SQLite persistence for derivatives metrics.

Repository pattern: all database access for coinglass_data goes here.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from finbar.core.domain.entities.derivatives_metrics import (
    DerivativesMetrics as DomainMetrics,
)
from finbar.core.domain.interfaces.derivatives_repository import (
    DerivativesRepository,
)
from finbar.infrastructure.tables.coinglass_data import CoinGlassData as OrmMetrics

logger = logging.getLogger(__name__)


# ── Mapper functions ──────────────────────────────────────────────────────


def _domain_to_orm(metrics: DomainMetrics) -> OrmMetrics:
    """Convert domain DerivativesMetrics to ORM model."""
    return OrmMetrics(
        symbol=metrics.symbol,
        timestamp=metrics.timestamp,
        interval=metrics.interval,
        open_interest=metrics.open_interest,
        open_interest_delta_1h=metrics.open_interest_delta_1h,
        open_interest_delta_24h=metrics.open_interest_delta_24h,
        cumulative_volume_delta=metrics.cumulative_volume_delta,
        funding_rate=metrics.funding_rate,
        long_short_ratio=metrics.long_short_ratio,
        liquidations_long_1h=metrics.liquidations_long_1h,
        liquidations_short_1h=metrics.liquidations_short_1h,
        liquidations_long_24h=metrics.liquidations_long_24h,
        liquidations_short_24h=metrics.liquidations_short_24h,
    )


def _orm_to_domain(orm: OrmMetrics) -> DomainMetrics:
    """Convert ORM model to domain DerivativesMetrics."""
    return DomainMetrics(
        symbol=orm.symbol,
        timestamp=orm.timestamp,
        interval=orm.interval,
        open_interest=orm.open_interest,
        open_interest_delta_1h=orm.open_interest_delta_1h,
        open_interest_delta_24h=orm.open_interest_delta_24h,
        cumulative_volume_delta=orm.cumulative_volume_delta,
        funding_rate=orm.funding_rate,
        long_short_ratio=orm.long_short_ratio,
        liquidations_long_1h=orm.liquidations_long_1h,
        liquidations_short_1h=orm.liquidations_short_1h,
        liquidations_long_24h=orm.liquidations_long_24h,
        liquidations_short_24h=orm.liquidations_short_24h,
    )


class SqlCoinGlassRepository(DerivativesRepository):
    """SQLite repository for derivatives market metrics."""

    def __init__(self, db: Session):
        """Create the repository with a database session."""
        self._db = db

    def save(self, metrics: DomainMetrics) -> None:
        """Insert or update a single derivatives metrics record."""
        orm = _domain_to_orm(metrics)
        self._db.merge(orm)
        self._db.commit()

    def save_batch(self, metrics_list: list[DomainMetrics]) -> None:
        """Insert or update a batch of derivatives metrics."""
        for metrics in metrics_list:
            self._db.merge(_domain_to_orm(metrics))
        self._db.commit()

    def find(
        self,
        symbol: str,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[DomainMetrics]:
        """Query derivatives metrics for a symbol with optional time range."""
        stmt = select(OrmMetrics).where(OrmMetrics.symbol == symbol)
        if start_time:
            stmt = stmt.where(OrmMetrics.timestamp >= start_time)
        if end_time:
            stmt = stmt.where(OrmMetrics.timestamp < end_time)
        stmt = stmt.order_by(OrmMetrics.timestamp)
        rows = self._db.execute(stmt).scalars().all()
        return [_orm_to_domain(row) for row in rows]

    def latest(self, symbol: str) -> DomainMetrics | None:
        """Return the most recent derivatives metrics for a symbol."""
        stmt = (
            select(OrmMetrics)
            .where(OrmMetrics.symbol == symbol)
            .order_by(OrmMetrics.timestamp.desc())
            .limit(1)
        )
        row = self._db.execute(stmt).scalars().first()
        return _orm_to_domain(row) if row else None
