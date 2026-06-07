"""SqlBacktestResultRepository — SQLite-backed backtest result persistence."""

import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from finbar.infrastructure.tables.backtest_result import BacktestResult as OrmResult


class SqlBacktestResultRepository:
    """Persist and retrieve backtest results from SQLite."""

    def __init__(self, db: Session):
        """Create the repository with a database session."""
        self._db = db

    def save(self, result_id: str, result: dict) -> None:
        """Insert or replace a backtest result."""
        result_json = json.dumps(result)
        existing = self._db.execute(
            select(OrmResult).where(OrmResult.result_id == result_id)
        ).scalar_one_or_none()
        if existing:
            existing.result_json = result_json
            existing.strategy_name = str(result.get("strategy_name", ""))
            existing.symbol = str(result.get("symbol", ""))
            existing.interval = str(result.get("interval", ""))
            existing.start_date = str(result.get("start_date", ""))
            existing.end_date = str(result.get("end_date", ""))
        else:
            self._db.add(
                OrmResult(
                    result_id=result_id,
                    strategy_name=str(result.get("strategy_name", "")),
                    symbol=str(result.get("symbol", "")),
                    interval=str(result.get("interval", "")),
                    start_date=str(result.get("start_date", "")),
                    end_date=str(result.get("end_date", "")),
                    result_json=result_json,
                    created_at=str(result.get("start_date", "")),
                )
            )
        self._db.commit()

    def get(self, result_id: str) -> dict | None:
        """Return a full backtest result by ID."""
        orm = self._db.execute(
            select(OrmResult).where(OrmResult.result_id == result_id)
        ).scalar_one_or_none()
        if orm is None:
            return None
        return json.loads(orm.result_json)

    def list_metadata(
        self,
        symbol: str | None = None,
        strategy_name: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Return compact metadata records."""
        query = select(OrmResult).order_by(OrmResult.id.desc())
        if symbol:
            query = query.where(OrmResult.symbol == symbol.upper())
        if strategy_name:
            query = query.where(OrmResult.strategy_name == strategy_name)
        query = query.limit(limit)
        rows = self._db.execute(query).scalars()
        return [
            {
                "result_id": row.result_id,
                "created_at": row.created_at,
                "strategy_name": row.strategy_name,
                "symbol": row.symbol,
                "interval": row.interval,
                "start_date": row.start_date,
                "end_date": row.end_date,
            }
            for row in rows
        ]

    def delete(self, result_id: str) -> bool:
        """Remove a result. Return True if a row was deleted."""
        result = self._db.execute(
            delete(OrmResult).where(OrmResult.result_id == result_id)
        )
        self._db.commit()
        return bool(result.rowcount)
