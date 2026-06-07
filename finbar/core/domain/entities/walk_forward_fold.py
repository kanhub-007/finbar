"""WalkForwardFold — result for a single walk-forward train/test split.

Pure dataclass — no behavior, no ORM, no framework dependencies.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WalkForwardFold:
    """A single walk-forward fold with train and test results.

    The training window is used for grid search to find the best parameters.
    Those parameters are then tested out-of-sample on the test window.

    Attributes:
        fold_index: Zero-based fold number.
        train_start: Timestamp of the first training bar.
        train_end: Timestamp of the last training bar.
        test_start: Timestamp of the first test bar.
        test_end: Timestamp of the last test bar.
        train_bars: Number of bars in the training window.
        test_bars: Number of bars in the test window.
        best_params: Dictionary of the best parameter values from grid search.
        is_sharpe: In-sample Sharpe ratio of the best params.
        is_total_return: In-sample total return of the best params.
        oos_sharpe: Out-of-sample Sharpe ratio.
        oos_total_return: Out-of-sample total return.
        oos_max_drawdown: Out-of-sample maximum drawdown.
        oos_win_rate: Out-of-sample win rate.
        oos_trades: Number of trades in the out-of-sample window.
        error: Error message if this fold failed.
        skipped: True if this fold was skipped due to insufficient bars.
    """

    fold_index: int
    train_start: str = ""
    train_end: str = ""
    test_start: str = ""
    test_end: str = ""
    train_bars: int = 0
    test_bars: int = 0
    best_params: dict = None  # type: ignore[assignment]
    is_sharpe: float = 0.0
    is_total_return: float = 0.0
    oos_sharpe: float = 0.0
    oos_total_return: float = 0.0
    oos_max_drawdown: float = 0.0
    oos_win_rate: float = 0.0
    oos_trades: int = 0
    error: str = ""
    skipped: bool = False

    def __post_init__(self):
        if self.best_params is None:
            object.__setattr__(self, "best_params", {})
