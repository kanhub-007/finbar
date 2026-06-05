"""Request DTO for starting a parameter optimization job."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StartOptimizationJobRequest:
    """Input for starting a grid search optimization job."""

    definition: str | dict
    """Strategy JSON string or parsed dictionary."""

    bars_artifact_id: str
    """Completed enrichment job ID for primary bars."""

    param_ranges: dict[str, dict[str, float]]
    """Parameter ranges keyed by param name, each with min/max/step."""

    metric: str = "sharpe_ratio"
    """Metric used to rank results."""

    search_method: str = "grid"
    """Search method: grid or random."""

    random_count: int = 20
    """Number of random samples for random search."""

    informative_bars_artifact_ids: dict[str, str] = field(default_factory=dict)
    """Completed enrichment job IDs keyed by informative timeframe alias."""

    initial_cash: float = 10000.0
    """Starting capital for backtests."""
