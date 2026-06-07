"""InMemoryBacktestResultStore — server-side backtest result cache with SQLite."""

from __future__ import annotations

import copy
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from finbar.core.application.backtest_result_projection import summary_from_result
from finbar.core.domain.interfaces.backtest_result_store import BacktestResultStore
from finbar.infrastructure.repositories.sql_backtest_result_repository import (
    SqlBacktestResultRepository,
)


class InMemoryBacktestResultStore(BacktestResultStore):
    """Thread-safe store for full backtest results with optional SQLite persistence."""

    def __init__(
        self,
        max_results: int = 100,
        session_factory: Callable[[], Session] | None = None,
    ):
        """Create a result store with optional persistent storage."""
        self._max_results = max(1, max_results)
        self._session_factory = session_factory
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def save(self, result: dict[str, Any]) -> str:
        """Persist a full backtest result and return a result ID."""
        result_id = f"bt_{uuid.uuid4().hex[:12]}"
        record = _record_from_result(result_id, result)
        with self._lock:
            self._records[result_id] = record
            self._enforce_max_results_locked()
        self._persist(result_id, result)
        return result_id

    def get(self, result_id: str) -> dict[str, Any] | None:
        """Return a full backtest result by ID."""
        with self._lock:
            record = self._records.get(result_id)
            if record is not None:
                return copy.deepcopy(record["result"])
        return self._load_from_sql(result_id)

    def list_results(
        self,
        symbol: str | None = None,
        strategy_name: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return compact metadata for stored results."""
        limit = max(1, min(limit, self._max_results))
        with self._lock:
            records = list(self._records.values())
        in_memory = [
            _public_record(record)
            for record in sorted(
                records, key=lambda item: item["created_at"], reverse=True
            )
            if _matches(record, symbol, strategy_name)
        ]
        if self._session_factory is not None:
            sql_results = self._with_repo(
                lambda repo: repo.list_metadata(symbol, strategy_name, limit)
            )
            merged = {r["result_id"]: r for r in sql_results}
            for r in in_memory:
                merged[r["result_id"]] = r
            return list(merged.values())[:limit]
        return in_memory[:limit]

    def delete(self, result_id: str) -> bool:
        """Remove a result from memory and persistent storage."""
        with self._lock:
            existed = result_id in self._records
            self._records.pop(result_id, None)
        if self._session_factory is not None:
            existed = self._with_repo(lambda repo: repo.delete(result_id)) or existed
        return existed

    def _enforce_max_results_locked(self) -> None:
        if len(self._records) <= self._max_results:
            return
        removable = sorted(self._records.values(), key=lambda item: item["created_at"])
        for record in removable:
            if len(self._records) <= self._max_results:
                return
            self._records.pop(record["result_id"], None)

    def _persist(self, result_id: str, result: dict[str, Any]) -> None:
        if self._session_factory is None:
            return
        self._with_repo(lambda repo: repo.save(result_id, result))

    def _load_from_sql(self, result_id: str) -> dict[str, Any] | None:
        if self._session_factory is None:
            return None
        return self._with_repo(lambda repo: repo.get(result_id))

    def _with_repo(self, callback):
        db = self._session_factory()
        try:
            return callback(SqlBacktestResultRepository(db))
        finally:
            db.close()


def _record_from_result(result_id: str, result: dict[str, Any]) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat()
    summary = summary_from_result(result)
    return {
        "result_id": result_id,
        "created_at": created_at,
        "strategy_name": str(result.get("strategy_name", "")),
        "symbol": str(result.get("symbol", "")),
        "interval": str(result.get("interval", "")),
        "start_date": str(result.get("start_date", "")),
        "end_date": str(result.get("end_date", "")),
        "summary": summary,
        "result": copy.deepcopy(result),
    }


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    summary = record["summary"]
    return {
        "result_id": record["result_id"],
        "created_at": record["created_at"],
        "strategy_name": record["strategy_name"],
        "symbol": record["symbol"],
        "interval": record["interval"],
        "start_date": record["start_date"],
        "end_date": record["end_date"],
        "bar_count": summary.get("bar_count", 0),
        "total_trades": summary.get("total_trades", 0),
        "total_return": summary.get("total_return"),
        "sharpe_ratio": summary.get("sharpe_ratio"),
        "max_drawdown": summary.get("max_drawdown"),
        "win_rate": summary.get("win_rate"),
    }


def _matches(
    record: dict[str, Any],
    symbol: str | None,
    strategy_name: str | None,
) -> bool:
    if symbol and record["symbol"].upper() != symbol.upper():
        return False
    if strategy_name and record["strategy_name"] != strategy_name:
        return False
    return True
