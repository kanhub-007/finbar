"""GetBacktestTradesUseCase — paginate stored backtest trades."""

from finbar.core.application.backtest_result_projection import page_items, sorted_trades
from finbar.core.application.dto.get_backtest_trades_result import (
    GetBacktestTradesResult,
)
from finbar.core.domain.interfaces.backtest_result_store import BacktestResultStore


class GetBacktestTradesUseCase:
    """Return sorted and paginated trades for a stored backtest result."""

    def __init__(self, store: BacktestResultStore):
        """Create the use case with a result store."""
        self._store = store

    def execute(
        self,
        result_id: str,
        page: int = 0,
        page_size: int = 50,
        sort_by: str = "entry_date",
        sort_dir: str = "asc",
    ) -> GetBacktestTradesResult:
        """Return one page of trades for a stored result."""
        result = self._store.get(result_id)
        if result is None:
            return GetBacktestTradesResult(
                found=False,
                result_id=result_id,
                error="Backtest result not found",
            )
        trades = sorted_trades(result.get("trades", []), sort_by, sort_dir)
        page_trades, page, page_size, total_pages, total = page_items(
            trades,
            page,
            page_size,
        )
        return GetBacktestTradesResult(
            found=True,
            result_id=result_id,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            total_trades=total,
            trade_count=len(page_trades),
            trades=page_trades,
        )
