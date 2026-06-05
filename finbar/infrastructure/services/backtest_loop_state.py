"""BacktestLoopState — mutable state carried through a backtest run."""

from finbar.infrastructure.services.backtest_position import BacktestPosition


class BacktestLoopState:
    """Mutable state carried through the backtest bar loop."""

    __slots__ = (
        "cash",
        "position",
        "trades",
        "equity_curve",
        "pending_signal",
        "peak_value",
    )

    def __init__(self, initial_cash: float) -> None:
        """Initialize loop state with starting cash and no open position."""
        self.cash = initial_cash
        self.position = BacktestPosition()
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.pending_signal: dict | None = None
        self.peak_value = initial_cash
