"""GetBacktestEquityUseCase — access stored backtest equity curves."""

from finbar.core.application.backtest_result_projection import equity_points, page_items
from finbar.core.application.dto.get_backtest_equity_result import (
    GetBacktestEquityResult,
)
from finbar.core.domain.interfaces.backtest_result_store import BacktestResultStore


class GetBacktestEquityUseCase:
    """Return downsampled or paginated equity points for a stored result."""

    def __init__(self, store: BacktestResultStore):
        """Create the use case with a result store."""
        self._store = store

    def execute(
        self,
        result_id: str,
        mode: str = "daily",
        page: int = 0,
        page_size: int = 500,
    ) -> GetBacktestEquityResult:
        """Return selected equity points for a stored result."""
        result = self._store.get(result_id)
        if result is None:
            return GetBacktestEquityResult(
                found=False,
                result_id=result_id,
                mode=mode,
                error="Backtest result not found",
            )
        selected = equity_points(result.get("equity_curve", []), mode)
        page_equity, page, page_size, total_pages, total = page_items(
            selected,
            page,
            page_size,
        )
        return GetBacktestEquityResult(
            found=True,
            result_id=result_id,
            mode=mode,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            total_equity_points=total,
            equity_count=len(page_equity),
            equity_curve=page_equity,
        )
