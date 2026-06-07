"""CachedPriceIndicatorJobRunner — execute cached-bar indicator jobs."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from finbar.core.domain.entities.indicator_job import IndicatorJob
from finbar.core.domain.entities.price_bar import PriceBar
from finbar.core.domain.interfaces.bar_frame_converter import BarFrameConverter
from finbar.core.domain.interfaces.indicator_calculator import IndicatorCalculator
from finbar.core.domain.interfaces.indicator_job_manager import IndicatorJobManager
from finbar.core.domain.interfaces.indicator_job_runner import IndicatorJobRunner
from finbar.core.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.domain.interfaces.strategy_feature_calculator import (
    StrategyFeatureCalculator,
)
from finbar.core.domain.services.content_hash import compute_artifact_hash
from finbar.infrastructure.repositories.sql_indicator_artifact_repository import (
    SqlIndicatorArtifactRepository,
)
from finbar.infrastructure.repositories.sql_price_cache_repository import (
    SqlPriceCacheRepository,
)


class CachedPriceIndicatorJobRunner(IndicatorJobRunner):
    """Run indicator jobs against cached bars using infrastructure services."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        manager: IndicatorJobManager,
        indicator_calculator: IndicatorCalculator,
        converter: BarFrameConverter,
        feature_calculator: StrategyFeatureCalculator,
        parser: StrategyDefinitionParser,
    ):
        """Create the runner with injected infrastructure collaborators."""
        self._session_factory = session_factory
        self._manager = manager
        self._indicator_calculator = indicator_calculator
        self._converter = converter
        self._feature_calculator = feature_calculator
        self._parser = parser

    async def run(self, job: IndicatorJob) -> None:
        """Run indicator computation without blocking the event loop."""
        try:
            await asyncio.to_thread(self._sync_run, job)
        except asyncio.CancelledError:
            self._manager.update(job, status="cancelled", error="Cancelled by user")
            raise

    def _sync_run(self, job: IndicatorJob) -> None:
        # Check for existing artifact with matching content hash
        content_hash = compute_artifact_hash(
            job.symbol,
            job.source,
            job.interval,
            job.metadata.get("indicators", []),
            job.timeframe_alias,
            job.start_date,
            job.end_date,
        )
        existing = self._try_reuse_artifact(job, content_hash)
        if existing:
            return

        _mark(self._manager, job, 5, "query_cached_prices", "Loading cached bars")
        bars = _load_cached_bars(job, self._session_factory)
        if not bars:
            _fail(
                self._manager,
                job,
                "No cached bars found for requested symbol/source/interval/date range",
            )
            return
        indicators, validation = self._resolve_indicators(job)
        if indicators is None:
            return
        result = self._apply_indicators(job, bars, indicators)
        if result is None:
            return
        indicator_bars, _indicator_frame = result
        enriched = _apply_features(
            job,
            indicator_bars,
            validation,
            self._manager,
            self._converter,
            self._feature_calculator,
        )
        enriched_bars, frame = enriched
        if enriched_bars is None:
            return
        self._manager.update(
            job,
            status="completed",
            progress_pct=100,
            stage="completed",
            message="Indicator computation completed",
            total_bar_count=len(enriched_bars),
        )
        self._manager.store_frame(job, frame)
        job.metadata["content_hash"] = content_hash
        self._manager.store_result(job, enriched_bars)

    def _resolve_indicators(self, job: IndicatorJob) -> tuple[list[str] | None, Any]:
        if job.mode == "selected":
            return list(job.metadata.get("indicators", [])), None
        if job.mode != "strategy_required":
            _fail(self._manager, job, f"Unsupported indicator computation '{job.mode}'")
            return None, None
        return self._strategy_required_indicators(job)

    def _strategy_required_indicators(
        self, job: IndicatorJob
    ) -> tuple[list[str] | None, Any]:
        definition = job.metadata.get("definition")
        if not definition:
            _fail(
                self._manager,
                job,
                "definition_json is required for strategy_required mode",
            )
            return None, None
        validation = self._parser.parse(definition, job.metadata.get("params", {}))
        if not validation.valid:
            self._manager.update(
                job,
                status="failed",
                progress_pct=100,
                stage="failed",
                error="Strategy definition is invalid",
                metadata={
                    **job.metadata,
                    "validation_errors": _diagnostics(validation),
                },
            )
            return None, None
        if job.timeframe_alias == "primary":
            return list(validation.primary_required_indicators), validation
        indicators = validation.informative_required_indicators.get(
            job.timeframe_alias, []
        )
        return list(indicators), validation

    def _apply_indicators(
        self,
        job: IndicatorJob,
        bars: list[dict],
        indicators: list[str],
    ) -> list[dict] | None:
        if not indicators:
            self._manager.update(job, indicators_applied=[])
            return bars
        _mark(
            self._manager,
            job,
            35,
            "calculate_indicators",
            _indicator_message(indicators),
        )
        try:
            frame = self._converter.bars_to_frame(bars)
            enriched = self._indicator_calculator.calculate(frame, indicators)
            result = self._converter.frame_to_bars(enriched)
        except Exception as exc:
            _fail(self._manager, job, f"Indicator calculation error: {exc}")
            return None
        self._manager.update(job, indicators_applied=list(indicators))
        return result, enriched


def _apply_features(
    job: IndicatorJob,
    bars: list[dict],
    validation,
    manager: IndicatorJobManager,
    converter: BarFrameConverter,
    feature_calculator: StrategyFeatureCalculator,
) -> tuple[list[dict] | None, Any]:
    """Return (bars, frame) tuple. Frame is for hot-path caching."""
    if not _should_apply_features(job, validation):
        try:
            frame = converter.bars_to_frame(bars)
            return bars, frame
        except Exception:
            return bars, None
    _mark(manager, job, 70, "calculate_features", "Calculating strategy features")
    try:
        frame = converter.bars_to_frame(bars)
        enriched = feature_calculator.calculate(frame, validation.definition.features)
        result = converter.frame_to_bars(enriched)
    except Exception as exc:
        _fail(manager, job, f"Feature calculation error: {exc}")
        return None, None
    manager.update(
        job,
        features_applied=[feature.name for feature in validation.definition.features],
    )
    return result


def _load_cached_bars(
    job: IndicatorJob,
    session_factory: Callable[[], Session],
) -> list[dict]:
    db = session_factory()
    try:
        repo = SqlPriceCacheRepository(db)
        bars = repo.query_bars(
            symbol=job.symbol,
            source=job.source,
            interval=job.interval,
            start_date=job.start_date,
            end_date=job.end_date,
        )
        return [_bar_to_dict(bar) for bar in bars]
    finally:
        db.close()

    def _try_reuse_artifact(self, job: IndicatorJob, content_hash: str) -> bool:
        """Return True and mark job completed if an artifact with the same
        hash already exists."""
        if self._session_factory is None or not content_hash:
            return False
        db = self._session_factory()
        try:
            existing_id = SqlIndicatorArtifactRepository(db).find_by_hash(content_hash)
        finally:
            db.close()
        if existing_id is None:
            return False
        bars = self._manager.get_artifact_bars(existing_id)
        if not bars:
            return False
        self._manager.update(
            job,
            status="completed",
            progress_pct=100,
            stage="completed",
            message="Reused existing artifact",
            total_bar_count=len(bars),
        )
        job.metadata["content_hash"] = content_hash
        self._manager.store_result(job, bars)
        return True


def _mark(
    manager: IndicatorJobManager,
    job: IndicatorJob,
    progress: int,
    stage: str,
    message: str,
) -> None:
    manager.update(
        job,
        status="running",
        progress_pct=progress,
        stage=stage,
        message=message,
    )


def _fail(manager: IndicatorJobManager, job: IndicatorJob, error: str) -> None:
    manager.update(
        job,
        status="failed",
        progress_pct=100,
        stage="failed",
        error=error,
    )


def _bar_to_dict(bar: PriceBar) -> dict:
    return {
        "timestamp": bar.timestamp,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


def _indicator_message(indicators: list[str]) -> str:
    return f"Calculating {len(indicators)} indicators"


def _should_apply_features(job: IndicatorJob, validation) -> bool:
    return (
        job.mode == "strategy_required"
        and job.timeframe_alias == "primary"
        and validation is not None
        and validation.definition is not None
        and bool(validation.definition.features)
    )


def _diagnostics(validation) -> list[dict[str, Any]]:
    return [
        {"path": error.path, "message": error.message, "code": error.code}
        for error in validation.errors
    ]
