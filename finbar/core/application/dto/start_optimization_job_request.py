"""Request DTO for starting a parameter optimization job."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StartOptimizationJobRequest:
    """Input for starting a grid search optimization job."""

    definition: str | dict
    """Strategy JSON string or parsed dictionary."""

    bars_artifact_id: str
    """Completed indicator job ID for primary bars."""

    param_ranges: dict[str, dict[str, float]]
    """Parameter ranges keyed by param name, each with min/max/step."""

    metric: str = "sharpe_ratio"
    """Metric used to rank results."""

    search_method: str = "grid"
    """Search method: grid or random."""

    random_count: int = 20
    """Number of random samples for random search."""

    informative_bars_artifact_ids: dict[str, str] = field(default_factory=dict)
    """Completed indicator job IDs keyed by informative timeframe alias."""

    interval: str = ""
    """Bar interval for result metadata and annualization."""

    risk_per_trade: float = 0.02
    """Fraction of portfolio to risk per trade."""

    leverage: float = 1.0
    """Leverage multiplier used by each backtest."""

    risk_mode: str = "fixed_equity_risk"
    """Risk sizing mode used by each backtest."""

    commission_pct: float = 0.0
    """Percentage commission per side for each backtest."""

    slippage_pct: float = 0.0
    """Directional slippage percentage for each backtest."""

    cap_explicit_size: bool = True
    """Cap explicit strategy sizes to buying power when true."""

    reject_oversized_explicit_orders: bool = False
    """Reject oversized explicit orders instead of capping them."""

    allow_negative_cash: bool = False
    """Allow backtests to overdraw cash when true."""

    market_calendar: str = "equity_regular_hours"
    """Market calendar used by annualization assumptions."""

    borrow_fee_annual_pct: float = 0.0
    """Annual borrow fee for short positions, expressed as a decimal."""

    margin_mode: str = "simplified"
    """Margin accounting mode: simplified or full."""

    initial_cash: float = 10000.0
    """Starting capital for backtests."""
