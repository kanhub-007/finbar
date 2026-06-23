"""SimulationState — mutable state carried through a backtest run."""

from __future__ import annotations

from finbar_strategy_runtime.simulation.backtest_diagnostic import BacktestDiagnostic
from finbar_strategy_runtime.simulation.pending_entry import PendingEntry
from finbar_strategy_runtime.simulation.pending_exit import PendingExit
from finbar_strategy_runtime.simulation.simulated_position import SimulatedPosition


class SimulationState:
    """Mutable state carried through the backtest bar loop."""

    __slots__ = (
        "initial_cash",
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
        "total_borrow_cost",
        "total_funding",
    )

    def __init__(self, initial_cash: float) -> None:
        """Initialize loop state with starting cash and no open position."""
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.position = SimulatedPosition()
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.pending_entry: PendingEntry | None = None
        self.pending_exit: PendingExit | None = None
        self.peak_value = initial_cash
        self.total_commission: float = 0.0
        self.total_slippage: float = 0.0
        self.used_margin: float = 0.0
        self.diagnostics: list[BacktestDiagnostic] = []
        self.total_borrow_cost: float = 0.0
        self.total_funding: float = 0.0

    def add_diagnostic(
        self,
        severity: str,
        code: str,
        message: str,
        date: str = "",
        metadata: dict | None = None,
    ) -> None:
        """Append a structured diagnostic to the loop state.

        Single point of diagnostic construction so the shape (incl. the
        ``date`` field) is consistent across PositionSizer, PositionOpener,
        and PositionExecutor. Sizer-emitted diagnostics previously shipped
        with ``date=""`` because they built the record directly; routing
        them through here fixes that silent divergence.
        """
        self.diagnostics.append(
            BacktestDiagnostic(
                severity=severity,
                code=code,
                message=message,
                date=date,
                metadata=metadata or {},
            )
        )
