"""CachedPriceIndicatorJobRunner — execute cached-bar indicator jobs."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from typing import Any

from finbar_strategy_runtime.domain.interfaces.bar_frame_converter import (
    BarFrameConverter,
)
from finbar_strategy_runtime.domain.interfaces.indicator_calculator import (
    IndicatorCalculator,
)
from finbar_strategy_runtime.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar_strategy_runtime.domain.interfaces.strategy_feature_calculator import (
    StrategyFeatureCalculator,
)
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    FAILED_INDICATORS_ATTR,
)
from sqlalchemy.orm import Session

from finbar.core.domain.entities.derivatives_metrics import (
    DERIVATIVES_FIELDS,
)
from finbar.core.domain.entities.indicator_job import IndicatorJob
from finbar.core.domain.entities.price_bar import PriceBar
from finbar.core.domain.interfaces.indicator_job_manager import IndicatorJobManager
from finbar.core.domain.interfaces.indicator_job_runner import IndicatorJobRunner
from finbar.infrastructure.repositories.sql_indicator_artifact_repository import (
    SqlIndicatorArtifactRepository,
)
from finbar.infrastructure.repositories.sql_price_cache_repository import (
    SqlPriceCacheRepository,
)

# Derivatives metric names that require pre-merged data from the repository.
# Sourced from the canonical DERIVATIVES_FIELDS on the entity.
_DERIVATIVES_INDICATORS = set(DERIVATIVES_FIELDS)


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
        derivatives_repository=None,
    ):
        """Create the runner with injected infrastructure collaborators.

        Args:
            derivatives_repository: Optional DerivativesRepository. When
                provided, derivatives metrics are merged onto the frame
                before indicator calculation (no-lookahead as-of join).
        """
        self._session_factory = session_factory
        self._manager = manager
        self._indicator_calculator = indicator_calculator
        self._converter = converter
        self._feature_calculator = feature_calculator
        self._parser = parser
        self._derivatives_repository = derivatives_repository

    async def run(self, job: IndicatorJob) -> None:
        """Run indicator computation without blocking the event loop."""
        try:
            await asyncio.to_thread(self._sync_run, job)
        except asyncio.CancelledError:
            self._manager.update(job, status="cancelled", error="Cancelled by user")
            raise
        except Exception as exc:
            self._manager.update(
                job,
                status="failed",
                progress_pct=100,
                stage="failed",
                error=f"Internal error: {exc}",
            )

    def _sync_run(self, job: IndicatorJob) -> None:
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
        enrichment_mode = job.metadata.setdefault("enrichment_mode", "batch_full_frame")
        # Content hash is deferred until after parsing so it can include
        # mode, definition, resolved indicators, params, and features —
        # preventing reuse of an unrelated artifact that merely shares
        # symbol/source/interval/date.
        content_hash = self._compute_content_hash(job, indicators, validation)
        existing = self._try_reuse_artifact(job, content_hash)
        if existing:
            return
        if enrichment_mode == "live_parity_streaming" and validation is not None:
            result = self._apply_causal_enrichment(job, bars, validation)
        else:
            result = self._apply_indicators(job, bars, indicators)
        if result is None:
            return
        indicator_bars, indicator_frame = result
        enriched = _apply_features(
            job,
            indicator_bars,
            validation,
            self._manager,
            self._converter,
            self._feature_calculator,
            base_frame=indicator_frame,
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

    def _apply_causal_enrichment(
        self,
        job: IndicatorJob,
        primary_bars: list[dict],
        validation,
    ) -> tuple[list[dict], Any] | None:
        """Run the causal streaming enricher and return (bars, frame).

        Loads any required informative bars from cache, then feeds all
        bars through ``CausalMultiTimeframeStreamingEnricher``. The
        resulting enriched frame carries the same schema as batch
        enrichment, making it a drop-in replacement for artifact consumers.
        """
        from finbar_strategy_runtime.indicators.causal_multi_timeframe_streaming_enricher import (  # noqa: E501
            CausalMultiTimeframeStreamingEnricher,
        )

        definition = validation.definition
        _mark(
            self._manager,
            job,
            10,
            "causal_enrichment",
            "Running causal streaming enrichment",
        )

        # Informative-timeframe jobs enrich their own bars with their own
        # indicators — no MTF merge. Only the primary job does MTF.
        is_primary = job.timeframe_alias == "primary"
        if not is_primary:
            alias = job.timeframe_alias
            info_indicators = validation.informative_required_indicators.get(
                alias, []
            )
            try:
                from dataclasses import replace as dc_replace

                from finbar_strategy_runtime.domain.entities.timeframe_declaration import (
                    TimeframeDeclaration,
                )

                single_tf_def = dc_replace(
                    definition,
                    timeframes=TimeframeDeclaration(
                        primary=job.interval, informative=[]
                    ),
                )
                frame = CausalMultiTimeframeStreamingEnricher.causal_enrich_bars(
                    primary_bars=primary_bars,
                    informative_bars={},
                    definition=single_tf_def,
                    primary_indicators=info_indicators,
                    informative_indicators={},
                    market_calendar="crypto_24_7",
                )
            except Exception as exc:
                _fail(
                    self._manager,
                    job,
                    f"Causal enrichment error: {exc}",
                )
                return None
            enriched_bars = self._converter.frame_to_bars(frame)
            _mark(
                self._manager,
                job,
                50,
                "causal_enrichment",
                f"Causal enrichment complete ({len(enriched_bars)} rows)",
            )
            return enriched_bars, frame

        info_bars: dict[str, list[dict]] = {}
        timeframes = definition.timeframes
        if timeframes is not None and timeframes.informative:
            for info in timeframes.informative:
                alias = info.alias
                interval = info.interval
                _mark(
                    self._manager,
                    job,
                    15,
                    "causal_enrichment",
                    f"Loading informative bars: {alias} ({interval})",
                )
                info_bars[alias] = _load_cached_bars_for_interval(
                    job.symbol,
                    job.source,
                    interval,
                    job.start_date,
                    job.end_date,
                    self._session_factory,
                )
                if not info_bars[alias]:
                    _fail(
                        self._manager,
                        job,
                        f"No cached {interval} bars for {alias}",
                    )
                    return None
        _mark(
            self._manager,
            job,
            20,
            "causal_enrichment",
            "Enriching bars causally",
        )
        try:
            frame = CausalMultiTimeframeStreamingEnricher.causal_enrich_bars(
                primary_bars=primary_bars,
                informative_bars=info_bars,
                definition=definition,
                primary_indicators=validation.primary_required_indicators,
                informative_indicators=validation.informative_required_indicators,
                market_calendar="crypto_24_7",
            )
        except Exception as exc:
            _fail(
                self._manager,
                job,
                f"Causal enrichment error: {exc}",
            )
            return None
        enriched_bars = self._converter.frame_to_bars(frame)
        _mark(
            self._manager,
            job,
            50,
            "causal_enrichment",
            f"Causal enrichment complete ({len(enriched_bars)} rows)",
        )
        return enriched_bars, frame

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
    ) -> tuple[list[dict], Any] | None:
        if not indicators:
            self._manager.update(job, indicators_applied=[])
            frame = self._converter.bars_to_frame(bars)
            return bars, frame
        _mark(
            self._manager,
            job,
            35,
            "calculate_indicators",
            _indicator_message(indicators),
        )
        try:
            frame = self._converter.bars_to_frame(bars)
            frame = self._merge_derivatives_if_needed(job, frame, indicators)
            enriched = self._indicator_calculator.calculate(frame, indicators)
            result = self._converter.frame_to_bars(enriched)
        except Exception as exc:
            _fail(self._manager, job, f"Indicator calculation error: {exc}")
            return None
        self._manager.update(job, indicators_applied=list(indicators))
        # Surface per-indicator failures (handler exceptions, unsatisfied
        # required columns) so they are visible instead of silent NaN
        # (spec 2026-06-16 Scenario 4 / ADR-6). The calculator attaches
        # them to the frame via pandas ``attrs``.
        failed = list(enriched.attrs.get(FAILED_INDICATORS_ATTR, []))
        if failed:
            self._manager.update(job, failed_indicators=failed)
        return result, enriched

    def _merge_derivatives_if_needed(self, job, frame, indicators: list[str]):
        """Merge derivatives data onto the frame if any derivatives metric
        is requested and a repository is configured.

        Uses the no-lookahead as-of merge: a derivatives value at T is
        only visible at bar T+1.
        """
        if not self._derivatives_repository:
            return frame
        if not any(name in _DERIVATIVES_INDICATORS for name in indicators):
            return frame
        deriv_rows = self._derivatives_repository.find(
            symbol=job.symbol,
        )
        if not deriv_rows:
            return frame
        from finbar.infrastructure.services.derivatives_merger import (
            merge_derivatives_asof,
        )

        interval = getattr(job, "interval", "1d") or "1d"
        return merge_derivatives_asof(frame, deriv_rows, interval=interval)

    def _compute_content_hash(
        self, job: IndicatorJob, indicators: list[str], validation
    ) -> str:
        """Return a content hash that includes all job inputs.

        Previous hash omitted mode, definition, resolved indicators, params,
        and features, allowing a strategy_required job to reuse an unrelated
        artifact.
        """
        payload = {
            "symbol": job.symbol.upper(),
            "source": job.source,
            "interval": job.interval,
            "mode": job.mode,
            "indicators": sorted(indicators),
            "timeframe_alias": job.timeframe_alias,
            "enrichment_mode": job.metadata.get("enrichment_mode", "batch_full_frame"),
            "start_date": job.start_date,
            "end_date": job.end_date,
            "definition": job.metadata.get("definition"),
            "params": dict(job.metadata.get("params", {})),
            # Include derivatives merge state so an artifact cached before
            # fetch_derivatives is not reused after data was persisted.
            "derivatives_merged": bool(
                self._derivatives_repository
                and any(n in _DERIVATIVES_INDICATORS for n in indicators)
            ),
        }
        if validation is not None and validation.definition is not None:
            features = [
                f.name for f in (validation.definition.features or [])
            ]
            payload["features"] = sorted(features)
        data = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()

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
        job.metadata.setdefault("enrichment_mode", "batch_full_frame")
        self._manager.store_result(job, bars)
        return True


def _apply_features(
    job: IndicatorJob,
    bars: list[dict],
    validation,
    manager: IndicatorJobManager,
    converter: BarFrameConverter,
    feature_calculator: StrategyFeatureCalculator,
    base_frame=None,
) -> tuple[list[dict] | None, Any]:
    """Return (bars, frame) tuple. Frame is for hot-path caching."""
    if not _should_apply_features(job, validation):
        try:
            if base_frame is not None:
                return bars, base_frame
            frame = converter.bars_to_frame(bars)
            return bars, frame
        except Exception:
            return bars, None
    _mark(manager, job, 70, "calculate_features", "Calculating strategy features")
    try:
        frame = converter.bars_to_frame(bars) if base_frame is None else base_frame
        enriched = feature_calculator.calculate(frame, validation.definition.features)
        result = converter.frame_to_bars(enriched)
    except Exception as exc:
        _fail(manager, job, f"Feature calculation error: {exc}")
        return None, None
    manager.update(
        job,
        features_applied=[feature.name for feature in validation.definition.features],
    )
    return result, enriched


def _load_cached_bars(
    job: IndicatorJob,
    session_factory: Callable[[], Session],
) -> list[dict]:
    return _load_cached_bars_for_interval(
        job.symbol,
        job.source,
        job.interval,
        job.start_date,
        job.end_date,
        session_factory,
    )


def _load_cached_bars_for_interval(
    symbol: str,
    source: str,
    interval: str,
    start_date: str | None,
    end_date: str | None,
    session_factory: Callable[[], Session],
) -> list[dict]:
    db = session_factory()
    try:
        repo = SqlPriceCacheRepository(db)
        bars = repo.query_bars(
            symbol=symbol,
            source=source,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
        )
        return [_bar_to_dict(bar) for bar in bars]
    finally:
        db.close()


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
