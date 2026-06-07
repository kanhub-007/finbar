"""SQLAlchemy ORM table for backtest results."""

from sqlalchemy import Column, Integer, String, Text

from finbar.infrastructure.data.connection import Base


class BacktestResult(Base):
    """Persisted server-side backtest result."""

    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(String, unique=True, nullable=False, index=True)
    strategy_name = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    interval = Column(String, nullable=False)
    start_date = Column(String, default="")
    end_date = Column(String, default="")
    result_json = Column(Text, nullable=False)
    created_at = Column(String, nullable=False)
