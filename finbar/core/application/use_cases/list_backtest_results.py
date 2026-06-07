"""ListBacktestResultsUseCase — discover stored backtest results."""

from finbar.core.application.dto.list_backtest_results_result import (
    ListBacktestResultsResult,
)
from finbar.core.domain.interfaces.backtest_result_store import BacktestResultStore


class ListBacktestResultsUseCase:
    """List compact metadata for stored backtest results."""

    def __init__(self, store: BacktestResultStore):
        """Create the use case with a result store."""
        self._store = store

    def execute(
        self,
        symbol: str | None = None,
        strategy_name: str | None = None,
        limit: int = 20,
    ) -> ListBacktestResultsResult:
        """Return stored backtest result metadata."""
        try:
            results = self._store.list_results(symbol, strategy_name, limit)
        except Exception as exc:
            return ListBacktestResultsResult(error=str(exc))
        return ListBacktestResultsResult(results=results)
