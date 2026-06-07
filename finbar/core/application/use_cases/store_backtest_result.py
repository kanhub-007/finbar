"""StoreBacktestResultUseCase — persist full results and return compact views."""

from typing import Any

from finbar.core.application.backtest_result_projection import compact_backtest_response
from finbar.core.application.dto.store_backtest_result_result import (
    StoreBacktestResultResult,
)
from finbar.core.domain.interfaces.backtest_result_store import BacktestResultStore


class StoreBacktestResultUseCase:
    """Store a full backtest result and return a compact response envelope."""

    def __init__(self, store: BacktestResultStore):
        """Create the use case with a result store."""
        self._store = store

    def execute(
        self,
        result: dict[str, Any],
        detail_level: str = "summary",
    ) -> StoreBacktestResultResult:
        """Store the result and return the requested compact representation."""
        try:
            result_id = self._store.save(result)
            response = compact_backtest_response(result_id, result, detail_level)
        except Exception as exc:
            return StoreBacktestResultResult(result_id="", error=str(exc))
        return StoreBacktestResultResult(result_id=result_id, response=response)
