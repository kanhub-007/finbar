"""Unit tests for walk-forward fold index computation and aggregation."""

import pytest

from finbar.core.domain.entities.walk_forward_fold import WalkForwardFold
from finbar.infrastructure.services.walk_forward_fold_helpers import (
    aggregate_folds,
    compute_fold_indices,
)


class TestComputeFoldIndices:
    """Tests for compute_fold_indices."""

    def test_returns_empty_for_too_few_bars(self):
        """Returns [] when total_bars < 3."""
        assert compute_fold_indices(2, 5, 0.7, "rolling") == []

    def test_returns_empty_for_too_few_folds(self):
        """Returns [] when folds < 2."""
        assert compute_fold_indices(100, 1, 0.7, "rolling") == []

    def test_rolling_produces_folds_with_train_and_test(self):
        """Rolling mode produces folds with both train and test windows."""
        indices = compute_fold_indices(100, 4, 0.7, "rolling")
        assert len(indices) >= 3  # 4 folds - 1 gap + catch-up
        for idx in indices:
            assert idx["train_count"] > 0
            assert idx["test_count"] > 0
            assert idx["train_end"] == idx["test_start"]

    def test_rolling_test_windows_are_contiguous(self):
        """Test windows of consecutive rolling folds follow train/test pattern."""
        indices = compute_fold_indices(100, 4, 0.7, "rolling")
        tests = [
            (i["test_start"], i["test_end"]) for i in indices if i["test_count"] > 0
        ]
        # Test windows should advance (each ends at or after previous ends)
        for i in range(len(tests) - 1):
            assert tests[i][1] <= tests[i + 1][1]

    def test_anchored_expands_training(self):
        """Anchored mode grows training window from start."""
        indices = compute_fold_indices(100, 3, 0.7, "anchored")
        assert len(indices) == 3
        train_ends = [i["train_end"] for i in indices]
        assert all(t <= n for t, n in zip(train_ends, train_ends[1:]))

    def test_fold_indices_bounded_by_total(self):
        """Indices never exceed total_bars."""
        for total in [30, 100, 500]:
            indices = compute_fold_indices(total, 5, 0.7, "rolling")
            for idx in indices:
                assert idx["test_end"] <= total


class TestAggregateFolds:
    """Tests for aggregate_folds."""

    def make_fold(
        self,
        index,
        oos_sharpe=1.0,
        oos_return=0.1,
        oos_dd=-0.05,
        oos_wr=0.5,
        oos_trades=5,
        is_sharpe=0.0,
        is_total_return=0.0,
        best_params=None,
        param_sensitivity=None,
        skipped=False,
        error="",
    ):
        return WalkForwardFold(
            fold_index=index,
            oos_sharpe=oos_sharpe,
            oos_total_return=oos_return,
            oos_max_drawdown=oos_dd,
            oos_win_rate=oos_wr,
            oos_trades=oos_trades,
            is_sharpe=is_sharpe,
            is_total_return=is_total_return,
            best_params=best_params or {"fast": 10, "slow": 30},
            param_sensitivity=param_sensitivity or {},
            skipped=skipped,
            error=error,
        )

    def test_empty_folds_returns_error(self):
        """Aggregating empty folds returns error result."""
        result = aggregate_folds([])
        assert result.folds_completed == 0
        assert result.error == "No folds completed successfully"

    def test_all_skipped_returns_error(self):
        """All folds skipped returns error result."""
        folds = [self.make_fold(0, skipped=True), self.make_fold(1, skipped=True)]
        result = aggregate_folds(folds)
        assert result.folds_completed == 0

    def test_single_fold_aggregates_correctly(self):
        """Single completed fold populates OOS metrics."""
        fold = self.make_fold(
            0, oos_sharpe=1.5, oos_return=0.2, oos_dd=-0.1, oos_wr=0.6, oos_trades=10
        )
        result = aggregate_folds([fold])
        assert result.folds_completed == 1
        assert result.oos_sharpe == pytest.approx(1.5)
        assert result.oos_total_return == pytest.approx(0.2)
        assert result.oos_max_drawdown == pytest.approx(-0.1)
        assert result.oos_win_rate == pytest.approx(0.6)
        assert result.oos_total_trades == 10

    def test_multiple_folds_compounds_returns(self):
        """OOS total return compounds across folds."""
        folds = [
            self.make_fold(0, oos_return=0.1),
            self.make_fold(1, oos_return=0.2),
            self.make_fold(2, oos_return=-0.05),
        ]
        result = aggregate_folds(folds)
        expected = (1.1 * 1.2 * 0.95) - 1.0
        assert result.oos_total_return == pytest.approx(expected)

    def test_multiple_folds_averages_metrics(self):
        """Sharpe, drawdown, win rate are averaged across folds."""
        folds = [
            self.make_fold(0, oos_sharpe=1.0, oos_dd=-0.1, oos_wr=0.6),
            self.make_fold(1, oos_sharpe=2.0, oos_dd=-0.2, oos_wr=0.4),
        ]
        result = aggregate_folds(folds)
        assert result.oos_sharpe == pytest.approx(1.5)
        assert result.oos_max_drawdown == pytest.approx(-0.15)
        assert result.oos_win_rate == pytest.approx(0.5)

    def test_is_oos_correlation_positive(self):
        """IS/OOS correlation is positive when IS and OOS align."""
        folds = [
            self.make_fold(0, is_sharpe=1.0, oos_sharpe=0.8, best_params={"a": 10}),
            self.make_fold(1, is_sharpe=2.0, oos_sharpe=1.5, best_params={"a": 10}),
            self.make_fold(2, is_sharpe=3.0, oos_sharpe=2.0, best_params={"a": 10}),
        ]
        result = aggregate_folds(folds)
        assert result.is_oos_correlation > 0.9

    def test_is_oos_correlation_negative(self):
        """IS/OOS correlation is negative when IS and OOS diverge."""
        folds = [
            self.make_fold(0, is_sharpe=1.0, oos_sharpe=-0.5, best_params={"a": 10}),
            self.make_fold(1, is_sharpe=2.0, oos_sharpe=-1.0, best_params={"a": 10}),
        ]
        result = aggregate_folds(folds)
        assert result.is_oos_correlation < 0.0

    def test_stability_full_when_params_identical(self):
        """Stability is 1.0 when all folds have identical best params."""
        folds = [
            self.make_fold(i, best_params={"fast": 10, "slow": 30}) for i in range(3)
        ]
        result = aggregate_folds(folds)
        assert result.stability == pytest.approx(1.0)

    def test_stability_lower_when_params_diverge(self):
        """Stability drops when best params vary across folds."""
        folds = [
            self.make_fold(0, best_params={"fast": 10}),
            self.make_fold(1, best_params={"fast": 30}),
            self.make_fold(2, best_params={"fast": 10}),
        ]
        result = aggregate_folds(folds)
        assert result.stability < 0.8

    def test_mixed_skipped_and_error_folds(self):
        """Skipped and error folds are excluded from aggregation."""
        folds = [
            self.make_fold(0, oos_sharpe=1.0, oos_return=0.1),
            self.make_fold(1, skipped=True),
            self.make_fold(2, error="backtest failed"),
            self.make_fold(3, oos_sharpe=2.0, oos_return=0.2),
        ]
        result = aggregate_folds(folds)
        assert result.folds_requested == 4
        assert result.folds_completed == 2

    def test_rank_correlation_identical(self):
        """Identical sensitivity produces rank correlation of 1.0."""
        folds = [
            self.make_fold(i, param_sensitivity={"a": 0.7, "b": 0.3}) for i in range(3)
        ]
        result = aggregate_folds(folds)
        assert result.avg_rank_correlation == pytest.approx(1.0)

    def test_rank_correlation_reversed(self):
        """Reversed rankings produce negative correlation."""
        folds = [
            self.make_fold(0, param_sensitivity={"a": 0.8, "b": 0.2}),
            self.make_fold(1, param_sensitivity={"a": 0.2, "b": 0.8}),
        ]
        result = aggregate_folds(folds)
        assert result.avg_rank_correlation == pytest.approx(-1.0)

    def test_rank_correlation_missing_data(self):
        """Empty sensitivity dicts produce 1.0 (not enough data)."""
        folds = [self.make_fold(i, param_sensitivity={}) for i in range(3)]
        result = aggregate_folds(folds)
        assert result.avg_rank_correlation == pytest.approx(1.0)

    def test_rank_correlation_single_fold(self):
        """Single fold always returns 1.0."""
        folds = [self.make_fold(0, param_sensitivity={"a": 0.5, "b": 0.5})]
        result = aggregate_folds(folds)
        assert result.avg_rank_correlation == pytest.approx(1.0)
