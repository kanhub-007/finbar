"""Request DTO for running a portfolio-level backtest."""

from dataclasses import dataclass, field

from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.portfolio_config import AssetAllocation


@dataclass(frozen=True)
class PortfolioBacktestRequest:
    """Input for a multi-asset portfolio backtest.

    Each asset in the portfolio runs its own strategy with a
    weight-proportional share of the initial capital. Results are
    aggregated into a portfolio-level equity curve.
    """

    assets: list[AssetAllocation] = field(default_factory=list)
    """Asset allocations, each with symbol, strategy, weight, and bars."""

    initial_cash: float = 100000.0
    """Starting capital for the whole portfolio."""

    interval: str = ""
    """Bar interval for annualization (e.g. '1d')."""

    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    """Shared execution settings for all strategies."""

    risk_per_trade: float = 0.02
    """Fraction of allocated capital to risk per trade."""
