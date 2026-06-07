"""BacktestLoopState — mutable state carried through a backtest run."""

from __future__ import annotations

from finbar.core.domain.entities.backtest_diagnostic import BacktestDiagnostic
from finbar.core.domain.entities.pending_entry import PendingEntry
from finbar.core.domain.entities.pending_exit import PendingExit
from finbar.infrastructure.services.backtest_position import BacktestPosition


class BacktestLoopState:
    """Mutable state carried through the backtest bar loop."""

    __slots__ = (
        "cash",
        "position",
        "trades",
        "equity_curve",
        "pending_entry",
        "pending_exit",
        "peak_value",
        "total_commission",
        "total_slippage",
        "used_margin",
        "diagnostics",
    )

    def __init__(self, initial_cash: float) -> None:
        """Initialize loop state with starting cash and no open position."""
        self.cash = initial_cash
        self.position = BacktestPosition()
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.pending_entry: PendingEntry | None = None
        self.pending_exit: PendingExit | None = None
        self.peak_value = initial_cash
        self.total_commission: float = 0.0
        self.total_slippage: float = 0.0
        self.used_margin: float = 0.0
        self.diagnostics: list[BacktestDiagnostic] = []
