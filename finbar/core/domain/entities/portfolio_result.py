"""PortfolioResult — aggregated result from a multi-asset portfolio backtest.

Pure dataclass — no behavior, no ORM, no framework dependencies.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PortfolioResult:
    """Aggregated results from a portfolio-level backtest.

    Attributes:
        total_return: Portfolio-level total return (decimal).
        sharpe_ratio: Portfolio-level annualized Sharpe ratio.
        max_drawdown: Portfolio-level maximum drawdown (decimal).
        equity_curve: Portfolio-level equity over time. Each dict has
            date, value, drawdown.
        per_asset_results: Dict mapping symbol to its individual
            BacktestResultDTO (or dict).
        correlation_matrix: List of lists of pairwise return correlations
            between assets. Row/column order matches assets list.
        turnover: Portfolio churn (fraction of portfolio traded per bar).
            Not computed in MVP; always 0.0.
        cash_drag: Fraction of portfolio held as uninvested cash on
            average. Not computed in MVP; always 0.0.
        error: Error message if the portfolio backtest failed.
    """

    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    equity_curve: list[dict] = field(default_factory=list)
    per_asset_results: dict = field(default_factory=dict)
    correlation_matrix: list[list[float]] = field(default_factory=list)
    turnover: float = 0.0
    cash_drag: float = 0.0
    error: str = ""
