"""GridSearchOptimizer — infrastructure grid search over strategy parameters."""

from __future__ import annotations

import asyncio
import itertools

from finbar.core.domain.entities.optimization_job import OptimizationJob
from finbar.core.domain.entities.optimization_result import OptimizationResult
from finbar.core.domain.entities.optimizer_config import OptimizerConfig
from finbar.core.domain.entities.param_range import ParamRange
from finbar.core.domain.interfaces.bar_frame_converter import BarFrameConverter
from finbar.core.domain.interfaces.indicator_artifact_provider import (
    IndicatorArtifactProvider,
)
from finbar.core.domain.interfaces.optimization_job_runner import (
    OptimizationJobRunner,
)
from finbar.core.domain.interfaces.timeframe_bar_merger import TimeframeBarMerger
from finbar.infrastructure.services.backtest_data_validator import (
    validate_required_data,
)

_MAX_COMBINATIONS = 100
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

_METRIC_ASCENDING = frozenset({"max_drawdown"})


class GridSearchOptimizer(OptimizationJobRunner):
    """Run a grid search over strategy parameters against pre-enriched bars."""

    def __init__(self, config: OptimizerConfig):
        """Create the optimizer from a configuration DTO."""
        self._parser = config.parser
        self._engine = config.engine
        self._converter = config.converter
        self._strategy_factory = config.strategy_factory
        self._manager = config.manager
        self._artifact_provider = config.artifact_provider
        self._timeframe_merger = config.timeframe_merger
        self._feature_calculator = config.feature_calculator

    async def run(self, job: OptimizationJob) -> None:
        """Run grid search in a thread so backtests don't block asyncio."""
        try:
            await asyncio.to_thread(self._sync_run, job)
        except asyncio.CancelledError:
            self._manager.update(job, status="cancelled", error="Cancelled by user")
            raise

    def _sync_run(self, job: OptimizationJob) -> None:
        ranges = _parse_ranges(job.metadata.get("param_ranges", {}))
        method = job.metadata.get("search_method", "grid")
        if method == "random":
            count = job.metadata.get("random_count", 20)
            combinations = _generate_random_combinations(ranges, count)
        else:
            combinations = _generate_combinations(ranges)
        if len(combinations) > _MAX_COMBINATIONS:
            self._manager.update(
                job,
                status="failed",
                error=(
                    f"Too many combinations ({len(combinations)}), "
                    f"max {_MAX_COMBINATIONS}"
                ),
            )
            return

        self._manager.update(
            job,
            status="running",
            total_combinations=len(combinations),
            message="Loading artifact bars",
        )
        primary_bars = _resolve_artifact(
            job.metadata.get("bars_artifact_id", ""),
            self._artifact_provider,
        )
        definition = job.metadata.get("definition", {})
        metric = job.metric
        if metric not in _RANKING_METRICS:
            metric = "sharpe_ratio"

        results: list[OptimizationResult] = []
        for idx, params in enumerate(combinations):
            self._manager.update(
                job,
                combinations_done=idx,
                progress_pct=int(idx / len(combinations) * 100),
                message=f"Testing combination {idx + 1}/{len(combinations)}",
            )
            result = self._backtest_one(
                definition,
                params,
                primary_bars,
                job.metadata,
            )
            results.append(result)

        results.sort(
            key=lambda r: (getattr(r, metric, 0) or 0),
            reverse=metric not in _METRIC_ASCENDING,
        )
        for rank, result in enumerate(results, 1):
            results[rank - 1] = OptimizationResult(
                rank=rank,
                params=result.params,
                sharpe_ratio=result.sharpe_ratio,
                sortino_ratio=result.sortino_ratio,
                total_return=result.total_return,
                max_drawdown=result.max_drawdown,
                profit_factor=result.profit_factor,
                win_rate=result.win_rate,
                calmar_ratio=result.calmar_ratio,
                total_trades=result.total_trades,
                error=result.error,
            )
        self._manager.update(
            job,
            status="completed",
            progress_pct=100,
            combinations_done=len(combinations),
            message="Optimization complete",
            results=results,
        )

    def _backtest_one(
        self,
        definition,
        params: dict,
        primary_bars: list[dict],
        metadata: dict,
    ) -> OptimizationResult:
        try:
            validation = self._parser.parse(definition, params)
            if not validation.valid or validation.definition is None:
                return OptimizationResult(
                    rank=0,
                    params=params,
                    error="Strategy validation failed with these params",
                )
            bars = primary_bars
            if (
                validation.definition.timeframes
                and validation.definition.timeframes.has_informative()
            ):
                bars = _merge_informative(
                    bars,
                    metadata,
                    validation,
                    self._artifact_provider,
                    self._converter,
                    self._timeframe_merger,
                )
            frame = self._converter.bars_to_frame(bars)
            if self._feature_calculator is not None and validation.definition.features:
                frame = self._feature_calculator.calculate(
                    frame, validation.definition.features
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
                initial_cash=metadata.get("initial_cash", 10000),
                warmup_bars=warmup.get("warmup_bars", 0),
                first_tradable=warmup.get("first_tradable", ""),
                **_execution_params(metadata),
            )
            return _metrics_from_raw(params, raw)
        except Exception as exc:
            return OptimizationResult(rank=0, params=params, error=str(exc))


def _parse_ranges(raw: dict) -> dict[str, ParamRange]:
    ranges: dict[str, ParamRange] = {}
    for name, spec in raw.items():
        if isinstance(spec, dict):
            ranges[name] = ParamRange(
                min=float(spec.get("min", 0)),
                max=float(spec.get("max", 0)),
                step=float(spec.get("step", 1)),
            )
    return ranges


def _generate_combinations(
    ranges: dict[str, ParamRange],
) -> list[dict[str, float]]:
    if not ranges:
        return [{}]
    names = list(ranges)
    values = [ranges[name].values() for name in names]
    combinations: list[dict[str, float]] = []
    for combo in itertools.product(*values):
        params = {}
        for name, value in zip(names, combo):
            params[name] = (
                int(value)
                if ranges[name].step == int(ranges[name].step) and value == int(value)
                else value
            )
        combinations.append(params)
    return combinations


def _generate_random_combinations(
    ranges: dict[str, ParamRange],
    count: int,
) -> list[dict[str, float]]:
    """Generate random parameter combinations."""
    if not ranges:
        return [{}]
    count = min(count, _MAX_COMBINATIONS)
    names = list(ranges)
    combinations: list[dict[str, float]] = []
    seen: set[tuple] = set()
    while len(combinations) < count and len(seen) < count * 10:
        params = {}
        key_parts = []
        for name in names:
            rng = ranges[name]
            vals = rng.random_values(1)
            value = vals[0]
            if rng.step == int(rng.step) and value == int(value):
                value = int(value)
            params[name] = value
            key_parts.append(value)
        key = tuple(key_parts)
        if key not in seen:
            seen.add(key)
            combinations.append(params)
    return combinations


def _resolve_artifact(
    artifact_id: str,
    provider: IndicatorArtifactProvider,
) -> list[dict]:
    if not artifact_id:
        raise ValueError("bars_artifact_id is required")
    bars = provider.get_artifact_bars(artifact_id)
    if bars is None:
        raise ValueError(f"Artifact bars not found: {artifact_id}")
    return bars


def _merge_informative(
    primary_bars: list[dict],
    metadata: dict,
    validation,
    artifact_provider: IndicatorArtifactProvider,
    converter: BarFrameConverter,
    merger: TimeframeBarMerger | None,
) -> list[dict]:
    if merger is None:
        raise ValueError("Multi-timeframe optimization is not wired")
    frame = converter.bars_to_frame(primary_bars)
    informative_ids = metadata.get("informative_bars_artifact_ids", {})
    for item in validation.definition.timeframes.informative:
        job_id = informative_ids.get(item.alias, "")
        if not job_id:
            raise ValueError(f"Missing informative artifact for '{item.alias}'")
        info_bars = artifact_provider.get_artifact_bars(job_id)
        if info_bars is None:
            raise ValueError(f"Informative artifact not found: {job_id}")
        info_frame = converter.bars_to_frame(info_bars)
        frame = merger.merge(frame, info_frame, item.interval)
    return converter.frame_to_bars(frame)


def _missing_columns(bars: list[dict], required: list[str]) -> list[str]:
    available: set[str] = set()
    for bar in bars:
        available.update(bar.keys())
    return [column for column in required if column not in available]


def _missing_frame_columns(frame, required: list[str]) -> list[str]:
    """Return required columns absent from a prepared frame."""
    return [column for column in required if column not in frame.columns]


def _warmup_error(warmup: dict) -> str:
    """Return a blocking warmup error message, or empty string."""
    if warmup.get("no_tradable_bars"):
        return "No tradable bars after warmup"
    missing = warmup.get("missing_after_warmup", [])
    if missing:
        return "Missing required data after warmup: " + ", ".join(missing)
    return ""


def _execution_params(metadata: dict) -> dict:
    """Extract backtest execution params from optimization metadata."""
    return {
        "interval": str(metadata.get("interval", "") or ""),
        "risk_per_trade": float(metadata.get("risk_per_trade", 0.02) or 0.02),
        "leverage": float(metadata.get("leverage", 1.0) or 1.0),
        "risk_mode": str(
            metadata.get("risk_mode", "fixed_equity_risk") or "fixed_equity_risk"
        ),
        "commission_pct": float(metadata.get("commission_pct", 0.0) or 0.0),
        "slippage_pct": float(metadata.get("slippage_pct", 0.0) or 0.0),
        "cap_explicit_size": bool(metadata.get("cap_explicit_size", True)),
        "reject_oversized_explicit_orders": bool(
            metadata.get("reject_oversized_explicit_orders", False)
        ),
        "allow_negative_cash": bool(metadata.get("allow_negative_cash", False)),
        "market_calendar": str(
            metadata.get("market_calendar", "equity_regular_hours") or ""
        ),
    }


def _metrics_from_raw(params: dict, raw: dict) -> OptimizationResult:
    return OptimizationResult(
        rank=0,
        params=params,
        sharpe_ratio=float(raw.get("sharpe_ratio", 0) or 0),
        sortino_ratio=float(raw.get("sortino_ratio", 0) or 0),
        total_return=float(raw.get("total_return", 0) or 0),
        max_drawdown=float(raw.get("max_drawdown", 0) or 0),
        profit_factor=(
            float(raw.get("profit_factor", 0) or 0) if raw.get("profit_factor") else 0.0
        ),
        win_rate=float(raw.get("win_rate", 0) or 0),
        calmar_ratio=float(raw.get("calmar_ratio", 0) or 0),
        total_trades=int(raw.get("total_trades", 0) or 0),
    )


def _warmup_check(frame, validation) -> dict:
    """Validate required data warmup for optimization backtests."""
    return validate_required_data(frame, validation.required_columns)
