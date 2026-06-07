"""GetBacktestSummaryUseCase — retrieve compact stored backtest summaries."""

from finbar.core.application.backtest_result_projection import compact_backtest_response
from finbar.core.application.dto.get_backtest_summary_result import (
    GetBacktestSummaryResult,
)
from finbar.core.domain.interfaces.backtest_result_store import BacktestResultStore


class GetBacktestSummaryUseCase:
    """Retrieve a compact or full response envelope for a stored result."""

    def __init__(self, store: BacktestResultStore):
        """Create the use case with a result store."""
        self._store = store

    def execute(
        self,
        result_id: str,
        detail_level: str = "summary",
    ) -> GetBacktestSummaryResult:
        """Return a stored backtest summary by ID."""
        result = self._store.get(result_id)
        if result is None:
            return GetBacktestSummaryResult(
                found=False,
                result_id=result_id,
                error="Backtest result not found",
            )
        response = compact_backtest_response(result_id, result, detail_level)
        return GetBacktestSummaryResult(
            found=True, result_id=result_id, response=response
        )
