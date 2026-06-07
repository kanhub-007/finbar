"""Pure mathematical correlation and statistics functions.

Used by walk-forward aggregation, portfolio correlation, and
any other domain logic that needs Pearson or Spearman correlation.
"""

from collections.abc import Sequence


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Compute Pearson correlation between two sequences.

    Returns 0.0 when fewer than 2 values or zero variance.
    """
    n = min(len(xs), len(ys))
    if n < 2:
        return 0.0
    xs_vals = xs[:n]
    ys_vals = ys[:n]
    mx = sum(xs_vals) / n
    my = sum(ys_vals) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs_vals, ys_vals))
    vx = sum((x - mx) ** 2 for x in xs_vals)
    vy = sum((y - my) ** 2 for y in ys_vals)
    if vx == 0 or vy == 0:
        return 0.0
    return cov / ((vx * vy) ** 0.5)


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Compute Spearman rank correlation between two rank lists.

    Returns 0.0 when fewer than 2 values or zero variance.
    """
    return pearson(xs, ys)


_RANKING_METRICS = frozenset(
    {
        "sharpe_ratio",
        "sortino_ratio",
        "total_return",
        "profit_factor",
        "win_rate",
        "calmar_ratio",
    }
)

_ASCENDING_METRICS = frozenset({"max_drawdown"})


def is_ranking_metric(name: str) -> bool:
    """Return True when `name` is a valid ranking metric."""
    return name in _RANKING_METRICS


def resolve_metric(name: str, default: str = "sharpe_ratio") -> str:
    """Return a canonical ranking metric name, falling back to default."""
    return name if name in _RANKING_METRICS else default


def sort_ascending(metric: str) -> bool:
    """Return True when the metric is sorted ascending (lower is better)."""
    return metric in _ASCENDING_METRICS
