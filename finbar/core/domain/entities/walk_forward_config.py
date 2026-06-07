"""WalkForwardConfig — configuration for walk-forward optimization.

Pure dataclass — no behavior, no ORM, no framework dependencies.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WalkForwardConfig:
    """Configuration for walk-forward parameter optimization.

    Walk-forward divides the bars into N folds, each with a training window
    (where grid search optimizes params) and a test window (where the best
    params are validated out-of-sample).

    Attributes:
        folds: Number of train/test splits (default 5).
        train_ratio: Fraction of each fold used for training (default 0.7).
        anchor: "rolling" (window slides forward) or "anchored" (training
            window expands from start).
        min_train_bars: Minimum bars required in the training window to
            run a fold. Folds below this are skipped.
        min_test_bars: Minimum bars required in the test window.
    """

    folds: int = 5
    train_ratio: float = 0.7
    anchor: str = "rolling"
    min_train_bars: int = 20
    min_test_bars: int = 5
