"""SQLAlchemy ORM table for cached symbol metadata.

Source-agnostic — works for both stock and crypto symbols.
"""

from sqlalchemy import Column, Float, Integer, String

from finbar.infrastructure.data.connection import Base


class SymbolInfo(Base):
    """Cached symbol/asset metadata — one row per symbol."""

    __tablename__ = "symbol_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, unique=True, nullable=False)
    company_name = Column(String, nullable=True)
    sector = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    exchange = Column(String, nullable=True)
    market_cap = Column(Float, nullable=True)
    fetched_at = Column(String, nullable=True)
