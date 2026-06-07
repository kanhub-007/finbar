"""Walk-forward fold index computation and result aggregation.

Pure functions with no external dependencies — extracted from
WalkForwardOptimizer to keep that file under 500 lines.
"""

from collections.abc import Sequence

from finbar.core.domain.entities.walk_forward_fold import WalkForwardFold
from finbar.core.domain.entities.walk_forward_result import WalkForwardResult
from finbar.core.domain.services.correlation import pearson as _pearson


def compute_fold_indices(
    total_bars: int,
    folds: int,
    train_ratio: float,
    anchor: str,
) -> list[dict]:
    """Compute train/test slice indices for walk-forward folds.

    Rolling: each fold is a fixed-size window that slides forward.
    Anchored: training window expands from start; test is fixed-size.
    """
    if total_bars < 3 or folds < 2:
        return []

    indices: list[dict] = []
    fold_size = total_bars // folds

    if anchor == "anchored":
        for i in range(folds):
            train_end = (i + 1) * fold_size
            test_end = min(train_end + fold_size, total_bars)
            indices.append(
                {
                    "train_start": 0,
                    "train_end": train_end,
                    "test_start": train_end,
                    "test_end": test_end,
                    "train_count": train_end,
                    "test_count": max(0, test_end - train_end),
                    "min_test": 1,
                }
            )
    else:
        for i in range(folds - 1):
            train_start = i * (fold_size // 2)
            train_end = train_start + int(fold_size * train_ratio)
            test_start = train_end
            test_end = min(test_start + fold_size, total_bars)
            indices.append(
                {
                    "train_start": train_start,
                    "train_end": train_end,
                    "test_start": test_start,
                    "test_end": test_end,
                    "train_count": train_end - train_start,
                    "test_count": max(0, test_end - test_start),
                    "min_test": 1,
                }
            )

        if indices and indices[-1]["test_end"] < total_bars:
            last_test_end = min(total_bars, indices[-1]["test_end"] + fold_size)
            last_train_start = max(0, indices[-1]["test_start"] - fold_size)
            indices.append(
                {
                    "train_start": last_train_start,
                    "train_end": indices[-1]["test_start"],
                    "test_start": indices[-1]["test_start"],
                    "test_end": last_test_end,
                    "train_count": indices[-1]["test_start"] - last_train_start,
                    "test_count": last_test_end - indices[-1]["test_start"],
                    "min_test": 1,
                }
            )

    return indices


def aggregate_folds(folds: Sequence[WalkForwardFold]) -> WalkForwardResult:
    """Aggregate fold results into a walk-forward result."""
    completed = [f for f in folds if not f.skipped and not f.error]
    if not completed:
        return WalkForwardResult(
            folds_requested=len(folds),
            folds_completed=0,
            folds=list(folds),
            error="No folds completed successfully",
        )

    oos_returns = [f.oos_total_return for f in completed]
    oos_sharpes = [f.oos_sharpe for f in completed]
    is_sharpes = [f.is_sharpe for f in completed]

    total_return = 1.0
    for r in oos_returns:
        total_return *= 1.0 + r
    total_return -= 1.0

    avg_oos_sharpe = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0.0
    avg_oos_dd = sum(f.oos_max_drawdown for f in completed) / len(completed)
    avg_oos_wr = sum(f.oos_win_rate for f in completed) / len(completed)
    total_trades = sum(f.oos_trades for f in completed)

    is_oos_corr = _pearson(is_sharpes, oos_sharpes) if len(completed) >= 2 else 0.0
    stability = _compute_stability(completed)
    rank_corr = _compute_rank_correlation(completed)

    return WalkForwardResult(
        folds_requested=len(folds),
        folds_completed=len(completed),
        folds=list(folds),
        oos_total_return=total_return,
        oos_sharpe=avg_oos_sharpe,
        oos_max_drawdown=avg_oos_dd,
        oos_win_rate=avg_oos_wr,
        oos_total_trades=total_trades,
        is_oos_correlation=is_oos_corr,
        stability=stability,
        avg_rank_correlation=rank_corr,
    )


def _compute_stability(folds: Sequence[WalkForwardFold]) -> float:
    """Measure parameter stability: fraction of best params within 20% of avg."""
    if len(folds) < 2:
        return 1.0
    param_names: set[str] = set()
    for f in folds:
        param_names.update(f.best_params.keys())
    if not param_names:
        return 1.0
    stable_count = 0
    total_values = 0
    for name in param_names:
        values = [float(f.best_params.get(name, 0.0)) for f in folds]
        avg = sum(values) / len(values)
        if avg == 0:
            stable_count += len(values)
            total_values += len(values)
            continue
        for v in values:
            if abs(v - avg) / abs(avg) <= 0.2:
                stable_count += 1
            total_values += 1
    return stable_count / total_values if total_values > 0 else 1.0


def _compute_rank_correlation(folds: Sequence[WalkForwardFold]) -> float:
    """Average Spearman rank correlation of param sensitivity across folds.

    For each fold, parameters are ranked by their sensitivity score.
    Spearman correlation is computed between every pair of fold rankings.
    The result is the average of all pairwise correlations.

    1.0 = params rank in exactly the same order across all folds.
    0.0 = rankings are random relative to each other.
    -1.0 = rankings are perfectly reversed.
    """
    param_names: set[str] = set()
    for f in folds:
        if not f.skipped and not f.error and f.param_sensitivity:
            param_names.update(f.param_sensitivity.keys())

    if len(param_names) < 2 or len(folds) < 2:
        return 1.0

    ordered_names = sorted(param_names)
    rankings: list[list[float]] = []
    for f in folds:
        if f.skipped or f.error or not f.param_sensitivity:
            continue
        scores = [f.param_sensitivity.get(n, 0.0) for n in ordered_names]
        rankings.append(_rank_values(scores))

    if len(rankings) < 2:
        return 1.0

    correlations: list[float] = []
    for i in range(len(rankings)):
        for j in range(i + 1, len(rankings)):
            corr = _spearman(rankings[i], rankings[j])
            correlations.append(corr)

    if not correlations:
        return 1.0
    return round(sum(correlations) / len(correlations), 4)


def _rank_values(values: list[float]) -> list[float]:
    """Convert a list of values to ranks (1 = highest value, avg rank for ties)."""
    if not values:
        return []
    indexed = [(v, i) for i, v in enumerate(values)]
    indexed.sort(key=lambda x: x[0], reverse=True)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) and indexed[j][0] == indexed[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[indexed[k][1]] = avg_rank
        i = j
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float:
    """Compute Spearman rank correlation between two rank lists."""
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / ((var_x * var_y) ** 0.5)


def compute_sensitivity(
    results: list,
    metric: str,
    ranges: dict,
) -> dict[str, float]:
    """Compute per-parameter sensitivity from grid search results.

    For each parameter, measures how much the objective varies across
    that parameter's values (holding others at their best). Normalizes
    so values sum to 1.0.

    Returns empty dict for fewer than 2 params or less than 2 results.
    """
    from finbar.core.domain.services.correlation import resolve_metric

    param_names = list(ranges.keys())
    if len(param_names) < 2 or len(results) < 2:
        return {}

    m = resolve_metric(metric)

    sensitivity: dict[str, float] = {}
    for name in param_names:
        values: set[float] = set()
        scores: dict[float, list[float]] = {}
        for r in results:
            if r.error:
                continue
            val = r.params.get(name)
            if val is not None:
                values.add(val)
                scores.setdefault(val, []).append(getattr(r, m, 0) or 0)
        if len(values) < 2:
            sensitivity[name] = 0.0
            continue
        means = [sum(v) / len(v) for v in scores.values()]
        sensitivity[name] = max(means) - min(means)

    total = sum(sensitivity.values())
    if total <= 0:
        return {}
    return {k: round(v / total, 4) for k, v in sensitivity.items()}
