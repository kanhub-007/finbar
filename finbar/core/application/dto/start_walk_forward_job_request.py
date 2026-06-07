"""Request DTO for starting a walk-forward optimization job."""

from dataclasses import dataclass, field

from finbar.core.domain.entities.execution_config import ExecutionConfig


@dataclass(frozen=True)
class StartWalkForwardJobRequest:
    """Input for starting a walk-forward optimization job.

    Shares the same fields as StartOptimizationJobRequest but adds
    walk-forward-specific configuration.
    """

    definition: str | dict
    """Strategy JSON string or parsed dictionary."""

    bars_artifact_id: str
    """Completed indicator job ID for primary bars."""

    param_ranges: dict[str, dict[str, float]]
    """Parameter ranges keyed by param name, each with min/max/step."""

    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    """Execution settings for each trial backtest."""

    metric: str = "sharpe_ratio"
    """Metric used to rank results in grid search and aggregate OOS."""

    search_method: str = "grid"
    """Search method for fold-level grid search: grid or random."""

    random_count: int = 20
    """Number of random samples for random search."""

    informative_bars_artifact_ids: dict[str, str] = field(default_factory=dict)
    """Completed indicator job IDs keyed by informative timeframe alias."""

    interval: str = ""
    """Bar interval for result metadata and annualization."""

    risk_per_trade: float = 0.02
    """Fraction of portfolio to risk per trade."""

    initial_cash: float = 10000.0
    """Starting capital for backtests."""

    wf_folds: int = 5
    """Number of walk-forward folds."""

    wf_train_ratio: float = 0.7
    """Fraction of each fold allocated to training."""

    wf_anchor: str = "rolling"
    """Fold anchor mode: rolling or anchored."""

    wf_min_train_bars: int = 20
    """Minimum bars required in training window."""

    wf_min_test_bars: int = 5
    """Minimum bars required in test window."""
