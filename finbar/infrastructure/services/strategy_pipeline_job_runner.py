"""StrategyPipelineJobRunner — execute strategy pipelines as background jobs."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

from finbar.core.application.use_cases.run_strategy_pipeline import (
    RunStrategyPipelineUseCase,
)
from finbar.infrastructure.services.strategy_pipeline_job import StrategyPipelineJob
from finbar.infrastructure.services.strategy_pipeline_job_manager import (
    StrategyPipelineJobManager,
)


class StrategyPipelineJobRunner:
    """Runs a strategy pipeline as a background job with progress updates."""

    def __init__(
        self,
        manager: StrategyPipelineJobManager,
        pipeline_factory: Any,
    ):
        """Create the runner.

        Args:
            manager: The job manager for status updates.
            pipeline_factory: Callable that returns a fresh
                RunStrategyPipelineUseCase instance.
        """
        self._manager = manager
        self._pipeline_factory = pipeline_factory

    async def run(
        self,
        job: StrategyPipelineJob,
        definition_json: str,
        symbol: str,
        source: str,
        start_date: str | None,
        end_date: str | None,
        initial_cash: float,
        risk_per_trade: float,
        leverage: float,
        detail_level: str,
        enrichment_mode: str,
    ) -> None:
        """Execute the full pipeline, updating job status at each stage."""
        manager = self._manager
        try:
            manager.update(
                job,
                status="running",
                progress_pct=5,
                stage="validation",
                message="Validating strategy...",
            )
            pipeline: RunStrategyPipelineUseCase = self._pipeline_factory()

            def _update_progress(pct: int, stage: str, msg: str) -> None:
                manager.update(
                    job,
                    progress_pct=pct,
                    stage=stage,
                    message=msg,
                )

            result = await pipeline.execute(
                definition_json,
                symbol,
                source,
                params_json={},
                start_date=start_date,
                end_date=end_date,
                initial_cash=initial_cash,
                risk_per_trade=risk_per_trade,
                leverage=leverage,
                detail_level=detail_level,
                enrichment_mode=enrichment_mode,
                progress_callback=_update_progress,
            )

            if result.complete:
                manager.update(
                    job,
                    status="completed",
                    progress_pct=100,
                    stage="complete",
                    message="Pipeline completed",
                    result=asdict(result),
                )
            else:
                error_msg = result.error or "Pipeline did not complete"
                manager.update(
                    job,
                    status="failed",
                    progress_pct=100,
                    stage=result.stage,
                    message=error_msg,
                    result=asdict(result),
                    error=error_msg,
                )
        except asyncio.CancelledError:
            manager.update(
                job,
                status="cancelled",
                error="Cancelled by user",
            )
            raise
        except Exception as exc:
            manager.update(
                job,
                status="failed",
                progress_pct=100,
                stage="failed",
                error=f"Pipeline error: {exc}",
            )
