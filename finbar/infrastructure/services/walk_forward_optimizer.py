"""WalkForwardOptimizer — walk-forward parameter validation.

For each fold, runs a grid search on the training window, then tests the
best parameters on the out-of-sample window. Aggregates OOS metrics and
overfitting diagnostics.
"""

from __future__ import annotations

import asyncio
import logging

from finbar.core.domain.entities.optimization_job import OptimizationJob
from finbar.core.domain.entities.optimization_result import OptimizationResult
from finbar.core.domain.entities.optimizer_config import OptimizerConfig
from finbar.core.domain.entities.walk_forward_config import WalkForwardConfig
from finbar.core.domain.entities.walk_forward_fold import WalkForwardFold
from finbar.core.domain.interfaces.optimization_job_runner import (
    OptimizationJobRunner,
)
from finbar.infrastructure.services.walk_forward_fold_helpers import (
    aggregate_folds,
    compute_fold_indices,
    compute_sensitivity,
)

logger = logging.getLogger(__name__)


class WalkForwardOptimizer(OptimizationJobRunner):
    """Run walk-forward optimization: grid search per fold, OOS validation."""

    def __init__(
        self,
        config: OptimizerConfig,
        wf_config: WalkForwardConfig = WalkForwardConfig(),
    ):
        """Create the walk-forward optimizer.

        Args:
            config: Optimizer wiring (same as GridSearchOptimizer).
            wf_config: Walk-forward split configuration.
        """
        self._parser = config.parser
        self._engine = config.engine
        self._converter = config.converter
        self._strategy_factory = config.strategy_factory
        self._manager = config.manager
        self._artifact_provider = config.artifact_provider
        self._timeframe_merger = config.timeframe_merger
        self._feature_calculator = config.feature_calculator
        self._wf = wf_config

    async def run(self, job: OptimizationJob) -> None:
        """Run walk-forward in a thread."""
        try:
            await asyncio.to_thread(self._sync_run, job)
        except asyncio.CancelledError:
            self._manager.update(job, status="cancelled", error="Cancelled by user")
            raise

    def _sync_run(self, job: OptimizationJob) -> None:
        metadata = job.metadata
        bars = _resolve_artifact(
            metadata.get("bars_artifact_id", ""),
            self._artifact_provider,
        )
        definition = metadata.get("definition", {})
        metric = str(metadata.get("metric", "sharpe_ratio") or "sharpe_ratio")
        folds_config = WalkForwardConfig(
            folds=int(metadata.get("wf_folds", self._wf.folds)),
            train_ratio=float(metadata.get("wf_train_ratio", self._wf.train_ratio)),
            anchor=str(metadata.get("wf_anchor", self._wf.anchor)),
            min_train_bars=int(
                metadata.get("wf_min_train_bars", self._wf.min_train_bars)
            ),
            min_test_bars=int(metadata.get("wf_min_test_bars", self._wf.min_test_bars)),
        )

        fold_indices = compute_fold_indices(
            len(bars), folds_config.folds, folds_config.train_ratio, folds_config.anchor
        )

        total = len([f for f in fold_indices if f["test_count"] > 0])
        if total == 0:
            self._manager.update(
                job,
                status="failed",
                error="Not enough bars for walk-forward: need at least 2 folds",
            )
            return

        self._manager.update(
            job,
            status="running",
            total_combinations=total,
        )

        fold_results: list[WalkForwardFold] = []
        runs_done = 0

        for idx, fold in enumerate(fold_indices):
            train_count = fold["train_count"]
            test_count = fold["test_count"]

            if train_count < folds_config.min_train_bars or test_count < fold.get(
                "min_test", folds_config.min_test_bars
            ):
                fold_results.append(
                    WalkForwardFold(
                        fold_index=idx,
                        train_bars=train_count,
                        test_bars=test_count,
                        skipped=True,
                    )
                )
                continue

            self._manager.update(
                job,
                combinations_done=runs_done,
                progress_pct=int(runs_done / total * 100),
                message=f"Fold {idx + 1}/{len(fold_indices)}: grid search",
            )

            train_bars = bars[fold["train_start"] : fold["train_end"]]
            test_bars = bars[fold["test_start"] : fold["test_end"]]

            fold_result = self._run_fold(
                idx,
                definition,
                train_bars,
                test_bars,
                metric,
                metadata,
            )
            fold_results.append(fold_result)
            runs_done += 1

        result = aggregate_folds(fold_results)
        self._manager.update(
            job,
            status="completed",
            progress_pct=100,
            combinations_done=total,
            message="Walk-forward complete",
            metadata={**job.metadata, "walk_forward_result": result},
        )

    def _run_fold(
        self,
        fold_index: int,
        definition: dict,
        train_bars: list[dict],
        test_bars: list[dict],
        metric: str,
        metadata: dict,
    ) -> WalkForwardFold:
        """Grid search on train, validate best params on test."""
        if not train_bars or not test_bars:
            return WalkForwardFold(fold_index=fold_index, skipped=True)

        train_start = _bar_timestamp(train_bars[0])
        train_end = _bar_timestamp(train_bars[-1])
        test_start = _bar_timestamp(test_bars[0])
        test_end = _bar_timestamp(test_bars[-1])

        try:
            grid_result, sensitivity = self._run_grid_search(
                definition, train_bars, metric, metadata
            )
            if grid_result is None or grid_result.error:
                return WalkForwardFold(
                    fold_index=fold_index,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    train_bars=len(train_bars),
                    test_bars=len(test_bars),
                    error=(
                        grid_result.error
                        if grid_result
                        else "Grid search returned no results"
                    ),
                )

            best_params = dict(grid_result.params)
            is_sharpe = float(grid_result.sharpe_ratio)
            is_return = float(grid_result.total_return)

            oos_result = self._run_oos(definition, best_params, test_bars, metadata)
            if oos_result.error:
                return WalkForwardFold(
                    fold_index=fold_index,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    train_bars=len(train_bars),
                    test_bars=len(test_bars),
                    best_params=best_params,
                    is_sharpe=is_sharpe,
                    is_total_return=is_return,
                    error=f"OOS backtest failed: {oos_result.error}",
                )

            return WalkForwardFold(
                fold_index=fold_index,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_bars=len(train_bars),
                test_bars=len(test_bars),
                best_params=best_params,
                is_sharpe=is_sharpe,
                is_total_return=is_return,
                oos_sharpe=float(oos_result.sharpe_ratio),
                oos_total_return=float(oos_result.total_return),
                oos_max_drawdown=float(oos_result.max_drawdown),
                oos_win_rate=float(oos_result.win_rate),
                oos_trades=int(oos_result.total_trades),
                param_sensitivity=sensitivity,
            )
        except Exception as exc:
            logger.exception("Fold %d failed", fold_index)
            return WalkForwardFold(
                fold_index=fold_index,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_bars=len(train_bars),
                test_bars=len(test_bars),
                error=str(exc),
            )

    def _run_grid_search(
        self,
        definition: dict,
        bars: list[dict],
        metric: str,
        metadata: dict,
    ) -> OptimizationResult | None:
        """Run a synchronous grid search directly on the training window.

        Returns (best_result, sensitivity_dict) where sensitivity maps
        param name to a normalized importance score (sums to 1.0).
        """
        from finbar.infrastructure.services.grid_search_optimizer import (
            _generate_combinations,
            _generate_random_combinations,
            _parse_ranges,
        )

        ranges = _parse_ranges(metadata.get("param_ranges", {}))
        method = metadata.get("search_method", "grid")
        if method == "random":
            count = metadata.get("random_count", 20)
            combinations = _generate_random_combinations(ranges, count)
        else:
            combinations = _generate_combinations(ranges)

        if len(combinations) > 100:
            return OptimizationResult(rank=0, params={}, error="Too many combinations")
        if not bars:
            return OptimizationResult(rank=0, params={}, error="No training bars")

        results: list[OptimizationResult] = []
        for params in combinations:
            result = self._backtest_with_bars(definition, params, bars, metadata)
            results.append(result)

        from finbar.core.domain.services.correlation import (
            resolve_metric,
            sort_ascending,
        )

        m = resolve_metric(metric)
        results.sort(
            key=lambda r: (getattr(r, m, 0) or 0),
            reverse=not sort_ascending(m),
        )

        if not results:
            return None, {}
        return results[0], compute_sensitivity(results, metric, ranges)

    def _backtest_with_bars(
        self,
        definition: dict,
        params: dict,
        bars: list[dict],
        metadata: dict,
    ) -> OptimizationResult:
        """Run a single backtest against the given bars slice."""
        from finbar.infrastructure.services.grid_search_optimizer import (
            _metrics_from_raw,
        )

        try:
            validation = self._parser.parse(definition, params)
            if not validation.valid or validation.definition is None:
                return OptimizationResult(
                    rank=0,
                    params=params,
                    error="Strategy validation failed with these params",
                )
            frame = self._converter.bars_to_frame(bars)
            if self._feature_calculator is not None and validation.definition.features:
                frame = self._feature_calculator.calculate(
                    frame, validation.definition.features
                )

            from finbar.infrastructure.services.grid_search_optimizer import (
                _missing_frame_columns,
                _warmup_check,
                _warmup_error,
            )

            missing = _missing_frame_columns(frame, validation.required_columns)
            if missing:
                return OptimizationResult(
                    rank=0,
                    params=params,
                    error=f"Missing columns: {', '.join(missing)}",
                )

            warmup = _warmup_check(frame, validation)
            warmup_error = _warmup_error(warmup)
            if warmup_error:
                return OptimizationResult(rank=0, params=params, error=warmup_error)

            executable_frame = frame
            if warmup.get("warmup_bars", 0) > 0:
                executable_frame = frame.iloc[int(warmup["warmup_bars"]) :]

            strategy = self._strategy_factory.create(validation.definition)
            raw = self._engine.run(
                df=executable_frame,
                strategy=strategy,
                initial_cash=float(metadata.get("initial_cash", 10000) or 10000),
                warmup_bars=int(warmup.get("warmup_bars", 0)),
                first_tradable=str(warmup.get("first_tradable", "") or ""),
                **self._exec_params(metadata),
            )
            return _metrics_from_raw(params, raw)
        except Exception as exc:
            return OptimizationResult(rank=0, params=params, error=str(exc))

    def _run_oos(
        self,
        definition: dict,
        params: dict,
        bars: list[dict],
        metadata: dict,
    ) -> OptimizationResult:
        """Backtest the best params on the OOS test window."""
        from finbar.infrastructure.services.grid_search_optimizer import (
            _merge_informative,
            _missing_frame_columns,
            _warmup_check,
            _warmup_error,
        )

        validation = self._parser.parse(definition, params)
        if not validation.valid or validation.definition is None:
            return OptimizationResult(
                rank=0,
                params=params,
                error="Strategy validation failed with best params",
            )

        merged_bars = bars
        if (
            validation.definition.timeframes
            and validation.definition.timeframes.has_informative()
        ):
            merged_bars = _merge_informative(
                bars,
                metadata,
                validation,
                self._artifact_provider,
                self._converter,
                self._timeframe_merger,
            )

        frame = self._converter.bars_to_frame(merged_bars)
        if self._feature_calculator is not None and validation.definition.features:
            frame = self._feature_calculator.calculate(
                frame, validation.definition.features
            )

        missing = _missing_frame_columns(frame, validation.required_columns)
        if missing:
            return OptimizationResult(
                rank=0,
                params=params,
                error=f"OOS missing columns: {', '.join(missing)}",
            )

        warmup = _warmup_check(frame, validation)
        warmup_error = _warmup_error(warmup)
        if warmup_error:
            return OptimizationResult(rank=0, params=params, error=warmup_error)

        executable_frame = frame
        if warmup.get("warmup_bars", 0) > 0:
            executable_frame = frame.iloc[int(warmup["warmup_bars"]) :]

        strategy = self._strategy_factory.create(validation.definition)
        raw = self._engine.run(
            df=executable_frame,
            strategy=strategy,
            initial_cash=float(metadata.get("initial_cash", 10000) or 10000),
            warmup_bars=int(warmup.get("warmup_bars", 0)),
            first_tradable=str(warmup.get("first_tradable", "") or ""),
            **self._exec_params(metadata),
        )

        from finbar.infrastructure.services.grid_search_optimizer import (
            _metrics_from_raw,
        )

        return _metrics_from_raw(params, raw)

    @staticmethod
    def _exec_params(metadata: dict) -> dict:
        from finbar.infrastructure.services.grid_search_optimizer import (
            _execution_params,
        )

        return _execution_params(metadata)


def _resolve_artifact(artifact_id: str, provider) -> list[dict]:
    if not artifact_id:
        raise ValueError("bars_artifact_id is required")
    bars = provider.get_artifact_bars(artifact_id)
    if bars is None:
        raise ValueError(f"Artifact bars not found: {artifact_id}")
    return bars


def _bar_timestamp(bar: dict) -> str:
    """Extract a display timestamp from a bar dict."""
    for key in ("timestamp", "date", "time"):
        val = bar.get(key, "")
        if val:
            return str(val)
    return ""
