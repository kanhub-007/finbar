"""Tests for optimization profit_factor handling (Finding 2).

A flawless strategy (no losing trades) has an infinite profit factor. It must
rank FIRST when the optimization metric is profit_factor, and the infinite value
must be normalised to None at the JSON serialization boundary.
"""

from finbar.core.application.use_cases.get_optimization_job_results import (
    _normalize_result,
)
from finbar.core.domain.services.correlation import sort_ascending
from finbar.infrastructure.services.grid_search_optimizer import _metrics_from_raw


def test_metrics_from_raw_preserves_infinite_profit_factor():
    # The engine emits None for an infinite profit factor (gross_loss == 0).
    result = _metrics_from_raw({"p": 1}, {"profit_factor": None, "total_trades": 3})
    assert result.profit_factor == float("inf")


def test_metrics_from_raw_finite_profit_factor_unchanged():
    result = _metrics_from_raw({"p": 1}, {"profit_factor": 2.5, "total_trades": 5})
    assert result.profit_factor == 2.5


def test_no_loss_strategy_ranks_first_on_profit_factor():
    """Replicates the optimizer's sort: a no-loss (inf profit factor) result
    must sort above every finite-profit-factor result when ranked descending."""
    no_loss = _metrics_from_raw({"p": "flawless"}, {"profit_factor": None})
    finite = _metrics_from_raw({"p": "normal"}, {"profit_factor": 2.5})
    results = [finite, no_loss]
    metric = "profit_factor"
    results.sort(
        key=lambda r: (getattr(r, metric, 0) or 0),
        reverse=not sort_ascending(metric),
    )
    assert results[0].params == {"p": "flawless"}
    assert results[0].profit_factor == float("inf")


def test_normalize_result_converts_infinite_profit_factor_to_none():
    raw = _normalize_result({"profit_factor": float("inf"), "rank": 1})
    assert raw["profit_factor"] is None


def test_normalize_result_leaves_finite_profit_factor_unchanged():
    raw = _normalize_result({"profit_factor": 2.5, "rank": 1})
    assert raw["profit_factor"] == 2.5
