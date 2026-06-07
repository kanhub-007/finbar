"""WalkForwardResult — aggregated walk-forward optimization results.

Pure dataclass — no behavior, no ORM, no framework dependencies.
"""

from dataclasses import dataclass, field

from finbar.core.domain.entities.walk_forward_fold import WalkForwardFold


@dataclass(frozen=True)
class WalkForwardResult:
    """Aggregated results from a walk-forward optimization.

    Attributes:
        folds_requested: Number of folds requested.
        folds_completed: Number of folds that produced results (not skipped).
        folds: Detailed results for each fold.
        oos_total_return: Compounded out-of-sample total return.
        oos_sharpe: OOS-period annualized Sharpe ratio.
        oos_max_drawdown: OOS-period maximum drawdown.
        oos_win_rate: OOS-period win rate.
        oos_total_trades: Total trades across all OOS windows.
        is_oos_correlation: Pearson correlation between IS and OOS Sharpe
            ratios across folds. Near-zero or negative suggests overfitting.
        stability: Fraction of folds where the best parameter set remained
            within 20% of the average best value. 1.0 = fully stable.
        avg_rank_correlation: Average Spearman rank correlation of parameter
            importance across folds. 1.0 = params ranked consistently.
        error: Error message if the walk-forward job failed entirely.
    """

    folds_requested: int = 0
    folds_completed: int = 0
    folds: list[WalkForwardFold] = field(default_factory=list)
    oos_total_return: float = 0.0
    oos_sharpe: float = 0.0
    oos_max_drawdown: float = 0.0
    oos_win_rate: float = 0.0
    oos_total_trades: int = 0
    is_oos_correlation: float = 0.0
    stability: float = 0.0
    avg_rank_correlation: float = 0.0
    error: str = ""
