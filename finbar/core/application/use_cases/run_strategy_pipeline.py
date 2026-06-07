"""RunStrategyPipelineUseCase — one-call validate → compute → backtest pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from finbar.core.application.dto.compute_strategy_indicators_result import (
    ComputeStrategyIndicatorsResult,
)
from finbar.core.application.dto.run_strategy_pipeline_result import (
    RunStrategyPipelineResult,
)
from finbar.core.application.use_cases.backtest_strategy_definition import (
    BacktestStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.compute_strategy_indicators import (
    ComputeStrategyIndicatorsUseCase,
)
from finbar.core.application.use_cases.store_backtest_result import (
    StoreBacktestResultUseCase,
)
from finbar.core.domain.interfaces.backtest_result_store import (
    BacktestResultStore,
)
from finbar.core.domain.interfaces.indicator_job_manager import IndicatorJobManager
from finbar.core.domain.interfaces.indicator_job_runner import IndicatorJobRunner
from finbar.core.domain.interfaces.price_cache_repository import (
    PriceCacheRepository,
)
from finbar.core.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser,
)

_POLL_INTERVAL = 0.5
_POLL_TIMEOUT = 300


class RunStrategyPipelineUseCase:
    """Orchestrate the full strategy pipeline for agent convenience.

    Dependencies are injected through the constructor following clean
    architecture. The optional price_cache_factory callable avoids
    holding a long-lived DB session.
    """

    def __init__(
        self,
        parser: StrategyDefinitionParser,
        manager: IndicatorJobManager,
        runner: IndicatorJobRunner,
        backtest_use_case: BacktestStrategyDefinitionUseCase,
        store: BacktestResultStore,
        price_cache_factory: Callable[[], PriceCacheRepository] | None = None,
    ):
        """Create the pipeline use case with injected collaborators."""
        self._parser = parser
        self._manager = manager
        self._runner = runner
        self._backtest = backtest_use_case
        self._store = store
        self._price_cache_factory = price_cache_factory

    async def execute(
        self,
        definition_json: str,
        symbol: str,
        source: str = "yfinance",
        params_json: dict[str, Any] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        initial_cash: float = 10000.0,
        risk_per_trade: float = 0.02,
        leverage: float = 1.0,
        detail_level: str = "summary",
    ) -> RunStrategyPipelineResult:
        """Run the full pipeline and return a compact result."""
        params = params_json or {}
        symbol = symbol.upper()

        validation = self._parser.parse(definition_json, params)
        if not validation.valid or validation.definition is None:
            return RunStrategyPipelineResult(
                complete=False,
                stage="validation",
                errors=[
                    {"path": e.path, "message": e.message, "code": e.code}
                    for e in validation.errors
                ],
                error="Strategy validation failed",
            )

        definition = validation.definition
        intervals = self._required_intervals(validation)
        missing = self._check_price_cache(symbol, source, intervals)
        if missing:
            return RunStrategyPipelineResult(
                complete=False,
                stage="price_cache",
                missing_price_data=missing,
                validation=self._validation_summary(
                    definition.name,
                    validation,
                ),
                error=(
                    "Price data missing for required intervals; "
                    "fetch first with fetch_price_history for each interval"
                ),
            )

        compute = ComputeStrategyIndicatorsUseCase(
            self._parser,
            self._manager,
            self._runner,
        )
        compute_result = compute.execute(
            definition_json,
            symbol,
            source,
            params,
            start_date,
            end_date,
        )
        if not compute_result.valid:
            return RunStrategyPipelineResult(
                complete=False,
                stage="indicators",
                errors=compute_result.errors,
                error="Indicator jobs could not be started",
            )

        await self._await_jobs(compute_result)
        primary_error = compute_result.primary.get("error")
        if primary_error:
            return RunStrategyPipelineResult(
                complete=False,
                stage="indicators",
                error=primary_error,
            )

        return await self._run_backtest(
            compute_result,
            definition_json,
            symbol,
            source,
            params,
            initial_cash,
            risk_per_trade,
            leverage,
            detail_level,
        )

    def _required_intervals(self, validation) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        timeframes = validation.definition.timeframes
        primary_interval = timeframes.primary if timeframes else "1d"
        result.append((primary_interval, "primary"))
        for alias, _ in validation.informative_required_indicators.items():
            interval = "1h"
            if timeframes and timeframes.informative:
                for item in timeframes.informative:
                    if getattr(item, "alias", "") == alias:
                        interval = str(getattr(item, "interval", "1h"))
                        break
            result.append((interval, alias))
        return result

    def _check_price_cache(
        self,
        symbol: str,
        source: str,
        intervals: list[tuple[str, str]],
    ) -> dict[str, str]:
        if self._price_cache_factory is None:
            return {}
        cache = self._price_cache_factory()
        missing: dict[str, str] = {}
        for interval, _alias in intervals:
            bars = cache.query_bars(
                symbol=symbol,
                source=source,
                interval=interval,
            )
            if not bars:
                missing[interval] = (
                    f"fetch_price_history('{symbol}', interval='{interval}', "
                    f"source='{source}')"
                )
        return missing

    async def _await_jobs(
        self, compute_result: ComputeStrategyIndicatorsResult
    ) -> None:
        job_ids = [compute_result.primary["job_id"]]
        job_ids.extend(info["job_id"] for info in compute_result.informative.values())
        elapsed = 0.0
        while True:
            all_done = True
            any_failed = False
            for jid in job_ids:
                job = self._manager.get(jid)
                if job is None:
                    any_failed = True
                    all_done = False
                    compute_result.primary["error"] = f"Job {jid} not found"
                elif job.status == "failed":
                    any_failed = True
                    compute_result.primary["error"] = job.error or "Job failed"
                elif job.status not in {"completed", "cancelled"}:
                    all_done = False
            if all_done or any_failed:
                return
            if elapsed >= _POLL_TIMEOUT:
                compute_result.primary["error"] = "Indicator jobs timed out"
                return
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

    async def _run_backtest(
        self,
        compute_result: ComputeStrategyIndicatorsResult,
        definition_json: str,
        symbol: str,
        source: str,
        params: dict[str, Any],
        initial_cash: float,
        risk_per_trade: float,
        leverage: float,
        detail_level: str,
    ) -> RunStrategyPipelineResult:
        from finbar.core.application.dto.backtest_strategy_definition_request import (
            BacktestStrategyDefinitionRequest,
        )
        from finbar.core.domain.entities.execution_config import ExecutionConfig

        primary_interval = compute_result.primary.get("interval", "1d")
        informative_artifact_ids: dict[str, str] = {
            alias: info["job_id"] for alias, info in compute_result.informative.items()
        }

        result = self._backtest.execute(
            BacktestStrategyDefinitionRequest(
                definition=definition_json,
                bars=[],
                execution=ExecutionConfig(
                    leverage_multiplier=leverage,
                    risk_mode="fixed_equity_risk",
                    commission_pct=0.0,
                    slippage_pct=0.0,
                ),
                symbol=symbol,
                interval=primary_interval,
                params=params,
                initial_cash=initial_cash,
                risk_per_trade=risk_per_trade,
                informative_bars=None,
                bars_artifact_id=compute_result.primary["job_id"],
                informative_bars_artifact_ids=informative_artifact_ids,
            )
        )

        if not result.valid or result.result is None:
            errors = [
                {"path": e.path, "message": e.message, "code": e.code}
                for e in result.errors
            ]
            msg = (
                "Backtest failed: " + ", ".join(e["message"] for e in errors)
                if errors
                else "Backtest result is empty"
            )
            return RunStrategyPipelineResult(
                complete=False,
                stage="backtest",
                errors=errors,
                error=msg,
            )

        stored = StoreBacktestResultUseCase(self._store).execute(
            asdict(result.result),
            detail_level,
        )

        return RunStrategyPipelineResult(
            complete=True,
            stage="complete",
            result_id=stored.result_id,
            response=stored.response,
            validation=self._validation_summary(
                compute_result.strategy_name,
                compute_result,
            ),
            indicators={
                "primary": compute_result.primary,
                "informative": compute_result.informative,
            },
        )

    @staticmethod
    def _validation_summary(
        name: str,
        data: Any,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "primary_required_indicators": getattr(
                data, "primary_required_indicators", []
            ),
            "informative_required_indicators": getattr(
                data, "informative_required_indicators", {}
            ),
        }
