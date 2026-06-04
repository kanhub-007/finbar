"""SQLAlchemy ORM table for cached OHLCV price bars.

Schema matches the plan:
- Partitioned by (symbol, source, interval)
- UNIQUE constraint on (symbol, source, interval, timestamp)
- Indexed for range queries
"""

from sqlalchemy import Column, Float, Index, Integer, String, UniqueConstraint

from finbar.infrastructure.data.connection import Base


class PriceBar(Base):
    """Cached OHLCV price bar — one row per timestamp."""

    __tablename__ = "price_bar"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    source = Column(String, nullable=False)
    interval = Column(String, nullable=False)
    timestamp = Column(String, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "symbol", "source", "interval", "timestamp", name="uq_price_bar"
        ),
        Index("ix_price_bar_symbol_source_interval", "symbol", "source", "interval"),
        Index("ix_price_bar_timestamp", "timestamp"),
    )
