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

    annualization_factor: float = 252.0
    """Number of return periods per year used for annualized metrics."""

    annualization_warning: str = ""
    """Warning describing fallback annualization assumptions, if any."""

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

    warmup_bars: int = 0
    """Number of bars excluded before indicators became valid."""

    first_tradable: str = ""
    """Timestamp of the first bar where all required indicators are valid."""

    total_commission: float = 0.0
    """Total absolute commission costs across all trades."""

    total_borrow_cost: float = 0.0
    """Total short borrow costs across all trades."""

    total_fees: float = 0.0
    """Total fee costs across all trades."""

    total_slippage: float = 0.0
    """Total absolute slippage impact across all trades."""

    realized_pnl: float = 0.0
    """Net realized PnL across closed trades."""

    cash: float = 0.0
    """Ending cash balance after all settlements."""

    ending_position_size: float = 0.0
    """Open position size at the end of the result."""

    reconciliation_error: float = 0.0
    """Difference between final value and initial cash plus realized PnL."""

    commission_pct: float = 0.0
    """Commission percentage used for this backtest."""

    slippage_pct: float = 0.0
    """Slippage percentage used for this backtest."""

    trades: list[dict] = field(default_factory=list)
    """List of trade records. Each trade has: entry_date, exit_date,
    entry_price, exit_price, size, pnl, pnl_pct, duration_bars, metadata."""

    equity_curve: list[dict] = field(default_factory=list)
    """List of equity snapshots over time. Each dict has: date, close,
    value, drawdown, position."""

    trust_diagnostics: dict = field(default_factory=dict)
    """Execution-model assumptions active during this backtest.
    Includes fill model, lookahead safety, cost model, warmup, and
    annualization metadata."""

    diagnostics: list[dict] = field(default_factory=list)
    """Structured execution diagnostics such as capped or rejected orders."""

    error: str | None = None
    """Error message if the backtest failed."""

    @property
    def is_profitable(self) -> bool:
        """True if the strategy produced a positive total return."""
        return self.total_return > 0.0
