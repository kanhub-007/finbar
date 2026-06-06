"""BacktestResultDTO — output from the run backtest use case.

Flat dataclass, JSON-serializable. Mirrors the backtest engine's output
but lives in the application layer (not domain).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BacktestResultDTO:
    """Structured backtest performance results.

    Includes trade-level detail and equity curve for AI analysis.
    All fields are JSON-serializable (no DataFrames, no numpy).
    """

    strategy_name: str = ""
    """Name of the strategy that was run."""

    symbol: str = ""
    """Ticker symbol."""

    interval: str = ""
    """Bar interval (e.g. "1d", "1h", "5min")."""

    start_date: str = ""
    """ISO-format start date of the backtest period."""

    end_date: str = ""
    """ISO-format end date of the backtest period."""

    bar_count: int = 0
    """Number of bars processed."""

    initial_cash: float = 0.0
    """Starting capital."""

    final_value: float = 0.0
    """Ending portfolio value."""

    total_return: float = 0.0
    """Total return as a decimal (e.g. 0.15 for 15%)."""

    annualized_return: float | None = None
    """Annualized return as a decimal."""

    total_trades: int = 0
    """Total number of completed trades."""

    winning_trades: int = 0
    """Number of profitable trades."""

    losing_trades: int = 0
    """Number of losing trades."""

    win_rate: float = 0.0
    """Win rate as a decimal (e.g. 0.55 for 55%)."""

    max_drawdown: float = 0.0
    """Maximum peak-to-trough drawdown as a decimal."""

    sharpe_ratio: float = 0.0
    """Annualized Sharpe ratio."""

    sortino_ratio: float = 0.0
    """Annualized Sortino ratio (downside deviation only)."""

    profit_factor: float = 0.0
    """Gross profit / gross loss."""

    calmar_ratio: float = 0.0
    """Annualized return / max drawdown."""

    position_sizing: str = ""
    """Diagnostic marker for position sizing method in use."""

    trades: list[dict] = field(default_factory=list)
    """List of trade records. Each trade has: entry_date, exit_date,
    entry_price, exit_price, size, pnl, pnl_pct, duration_bars, metadata."""

    equity_curve: list[dict] = field(default_factory=list)
    """List of equity snapshots over time. Each dict has: date, close,
    value, drawdown, position."""

    error: str | None = None
    """Error message if the backtest failed."""

    @property
    def is_profitable(self) -> bool:
        """True if the strategy produced a positive total return."""
        return self.total_return > 0.0
