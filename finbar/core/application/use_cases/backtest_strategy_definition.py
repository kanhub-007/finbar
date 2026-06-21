"""BacktestStrategyDefinitionUseCase — run unsaved JSON strategies."""

import logging
from dataclasses import replace
from typing import Any

from finbar_strategy_runtime.domain.entities.informative_timeframe import (
    InformativeTimeframe,
)
from finbar_strategy_runtime.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)
from finbar_strategy_runtime.domain.interfaces.bar_frame_converter import (
    BarFrameConverter,
)
from finbar_strategy_runtime.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar_strategy_runtime.domain.interfaces.strategy_definition_strategy_factory import (
    StrategyDefinitionStrategyFactory,
)
from finbar_strategy_runtime.domain.interfaces.strategy_feature_calculator import (
    StrategyFeatureCalculator,
)
from finbar_strategy_runtime.domain.interfaces.timeframe_bar_merger import (
    TimeframeBarMerger,
)
from finbar_strategy_runtime.indicators.multi_timeframe_bar_enricher import (
    MultiTimeframeBarEnricher,
)
from finbar_strategy_runtime.indicators.required_data_validator import (
    RequiredDataValidator,
)

from finbar.core.application.backtest_result_mapper import result_dto_from_raw
from finbar.core.application.dto.backtest_result import BacktestResultDTO
from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
)
from finbar.core.application.dto.backtest_strategy_definition_result import (
    BacktestStrategyDefinitionResult,
)
from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
from finbar.core.domain.interfaces.indicator_artifact_provider import (
    IndicatorArtifactProvider,
)
from finbar.infrastructure.services.backtest_data_validator import (
    validate_required_data,
)

logger = logging.getLogger(__name__)


class BacktestStrategyDefinitionUseCase:
    """Backtest a JSON strategy against OHLCV bars.

    Supports two paths:
    - Raw bars (no indicator columns): the enricher computes indicators,
      merges timeframes, and applies features inline.
    - Pre-enriched bars (from async indicator jobs): the legacy
      prepare_frame path frames and merges without recomputing indicators.

    Either path produces identical results for the same strategy + data.
    """

    def __init__(
        self,
        engine: BacktestEngine,
        converter: BarFrameConverter,
        strategy_factory: StrategyDefinitionStrategyFactory,
        parser: StrategyDefinitionParser,
        timeframe_merger: TimeframeBarMerger | None = None,
        artifact_provider: IndicatorArtifactProvider | None = None,
        feature_calculator: StrategyFeatureCalculator | None = None,
        enricher: MultiTimeframeBarEnricher | None = None,
        data_validator: RequiredDataValidator | None = None,
    ):
        """Create the use case with injected engine/converter/factory."""
        self._engine = engine
        self._converter = converter
        self._strategy_factory = strategy_factory
        self._parser = parser
        self._timeframe_merger = timeframe_merger
        self._artifact_provider = artifact_provider
        self._feature_calculator = feature_calculator
        self._enricher = enricher
        self._data_validator = data_validator

    def execute(
        self,
        request: BacktestStrategyDefinitionRequest,
    ) -> BacktestStrategyDefinitionResult:
        """Validate, verify columns, and run the supplied JSON strategy."""
        try:
            request = _resolve_artifact_bars(request, self._artifact_provider)
        except ValueError as exc:
            return BacktestStrategyDefinitionResult(
                valid=False,
                errors=[_err("$.bars_artifact_id", str(exc), "artifact_error")],
            )
        if not request.bars:
            return BacktestStrategyDefinitionResult(
                valid=False,
                errors=[_err("$.bars", "No bars provided", "no_bars")],
            )

        validation = self._parser.parse(request.definition, request.params)
        if not validation.valid or validation.definition is None:
            return BacktestStrategyDefinitionResult(
                valid=False,
                errors=validation.errors,
                required_indicators=validation.required_indicators,
                primary_required_indicators=validation.primary_required_indicators,
                informative_required_indicators=(
                    validation.informative_required_indicators
                ),
            )

        try:
            # Detect whether bars are raw OHLCV (no indicator columns) or
            # pre-enriched (from async indicator jobs). The enricher path
            # handles raw bars; the legacy path handles pre-enriched bars.
            use_enricher = self._enricher is not None and _bars_are_raw(
                request.bars, validation.required_columns
            )
            if use_enricher:
                frame = self._enricher.enrich(
                    primary_bars=request.bars,
                    informative_bars=request.informative_bars or {},
                    definition=validation.definition,
                    primary_required_indicators=(
                        validation.primary_required_indicators
                    ),
                    informative_required_indicators=(
                        validation.informative_required_indicators
                    ),
                )
            else:
                frame = self._prepare_frame(request, validation)
        except ValueError as exc:
            return BacktestStrategyDefinitionResult(
                valid=False,
                errors=[_err("$.bars", str(exc), "invalid_timeframe_bars")],
                required_indicators=validation.required_indicators,
                primary_required_indicators=validation.primary_required_indicators,
                informative_required_indicators=(
                    validation.informative_required_indicators
                ),
            )
        except Exception as exc:
            logger.warning("Failed to convert bars: %s", exc)
            return BacktestStrategyDefinitionResult(
                valid=False,
                errors=[_err("$.bars", f"Invalid bar data: {exc}", "invalid_bars")],
                required_indicators=validation.required_indicators,
                primary_required_indicators=validation.primary_required_indicators,
                informative_required_indicators=(
                    validation.informative_required_indicators
                ),
            )

        if not use_enricher:
            frame = self._resolve_and_compute_signals(
                frame, validation.definition
            )
        missing = [c for c in validation.required_columns if c not in frame.columns]
        if missing:
            return BacktestStrategyDefinitionResult(
                valid=False,
                errors=[
                    _err(
                        "$.bars",
                        "Supplied bars are missing required columns: "
                        + ", ".join(missing),
                        "missing_columns",
                    )
                ],
                required_indicators=validation.required_indicators,
                primary_required_indicators=validation.primary_required_indicators,
                informative_required_indicators=(
                    validation.informative_required_indicators
                ),
                missing_columns=missing,
            )

        if self._data_validator is not None and use_enricher:
            warmup = self._data_validator.validate(
                frame, validation.required_columns
            )
        else:
            warmup = validate_required_data(
                frame, validation.required_columns
            )
        warmup_errors = _warmup_errors(warmup)
        if warmup_errors:
            return BacktestStrategyDefinitionResult(
                valid=False,
                errors=warmup_errors,
                required_indicators=validation.required_indicators,
                primary_required_indicators=validation.primary_required_indicators,
                informative_required_indicators=(
                    validation.informative_required_indicators
                ),
                missing_columns=warmup.get("missing_after_warmup", []),
            )

        return _run_backtest(
            request,
            validation,
            frame,
            self._strategy_factory,
            self._engine,
            warmup,
        )

    def _resolve_and_compute_signals(self, frame: Any, definition) -> Any:
        """Compute signals (derived formula columns) on the frame."""
        if self._feature_calculator is not None and definition.features:
            logger.info(
                "Computing %d features: %s",
                len(definition.features),
                [f.name for f in definition.features],
            )
            frame = self._feature_calculator.calculate(frame, definition.features)
            computed = [f.name for f in definition.features if f.name in frame.columns]
            missing_feats = [
                f.name for f in definition.features if f.name not in frame.columns
            ]
            logger.info("Features computed: %s", computed)
            if missing_feats:
                logger.warning("Features missing after compute: %s", missing_feats)
        else:
            fc = self._feature_calculator
            feats = definition.features if definition else []
            logger.info(
                "Feature computation SKIPPED: fc=%s, features=%d",
                "present" if fc else "None",
                len(feats),
            )
        return frame

    def _prepare_frame(
        self,
        request: BacktestStrategyDefinitionRequest,
        validation,
    ) -> Any:
        primary_frame = self._converter.bars_to_frame(request.bars)
        timeframes = validation.definition.timeframes
        if timeframes is None or not timeframes.has_informative():
            if request.informative_bars:
                raise ValueError(
                    "informative_bars were supplied but strategy has no timeframes"
                )
            return primary_frame
        if self._timeframe_merger is None:
            raise ValueError("multi-timeframe backtesting is not wired")
        _validate_informative_payload_shape(request.informative_bars, timeframes)
        frame = primary_frame
        for item in timeframes.informative:
            bars = _select_informative_bars(request.informative_bars, item)
            info_frame = self._converter.bars_to_frame(bars)
            frame = self._timeframe_merger.merge(frame, info_frame, item.interval)
        return frame


def _resolve_artifact_bars(
    request: BacktestStrategyDefinitionRequest,
    provider: IndicatorArtifactProvider | None,
) -> BacktestStrategyDefinitionRequest:
    bars = request.bars
    informative_bars = request.informative_bars
    if request.bars_artifact_id:
        bars = _artifact_bars(request.bars_artifact_id, provider)
    if request.informative_bars_artifact_ids:
        informative_bars = {
            alias: _artifact_bars(job_id, provider)
            for alias, job_id in request.informative_bars_artifact_ids.items()
        }
    if bars is request.bars and informative_bars is request.informative_bars:
        return request
    return replace(request, bars=bars, informative_bars=informative_bars)


def _artifact_bars(
    job_id: str,
    provider: IndicatorArtifactProvider | None,
) -> list[dict]:
    if provider is None:
        raise ValueError("Artifact-backed backtesting is not wired")
    job = provider.get_artifact_job(job_id)
    if job is None:
        raise ValueError(f"Artifact job not found: {job_id}")
    if job.status != "completed":
        raise ValueError(f"Artifact job {job_id} is not complete: {job.status}")
    bars = provider.get_artifact_bars(job_id)
    if bars is None:
        raise ValueError(f"Artifact bars not found: {job_id}")
    return bars


def _run_backtest(
    request: BacktestStrategyDefinitionRequest,
    validation,
    frame: Any,
    strategy_factory: StrategyDefinitionStrategyFactory,
    engine: BacktestEngine,
    warmup: dict | None = None,
) -> BacktestStrategyDefinitionResult:
    strategy = strategy_factory.create(validation.definition)
    try:
        raw_result = engine.run(
            df=frame,
            strategy=strategy,
            initial_cash=request.initial_cash,
            risk_per_trade=request.risk_per_trade,
            leverage=request.execution.leverage_multiplier,
            risk_mode=request.execution.risk_mode,
            commission_pct=request.execution.commission_pct,
            slippage_pct=request.execution.slippage_pct,
            cap_explicit_size=request.execution.cap_explicit_size,
            reject_oversized_explicit_orders=(
                request.execution.reject_oversized_explicit_orders
            ),
            allow_negative_cash=request.execution.allow_negative_cash,
            market_calendar=request.execution.market_calendar,
            borrow_fee_annual_pct=request.execution.borrow_fee_annual_pct,
            margin_mode=request.execution.margin_mode,
            maintenance_margin_pct=request.execution.maintenance_margin_pct,
            enable_funding=request.execution.enable_funding,
            funding_rate=request.execution.funding_rate,
            interval=request.interval,
            warmup_bars=warmup.get("warmup_bars", 0) if warmup else 0,
            first_tradable=warmup.get("first_tradable", "") if warmup else "",
        )
    except Exception as exc:
        logger.exception("JSON strategy backtest failed")
        return BacktestStrategyDefinitionResult(
            valid=True,
            result=BacktestResultDTO(
                strategy_name=validation.definition.name,
                error=f"Backtest error: {exc}",
            ),
            required_indicators=validation.required_indicators,
            primary_required_indicators=validation.primary_required_indicators,
            informative_required_indicators=validation.informative_required_indicators,
        )

    raw_result["symbol"] = request.symbol
    raw_result["interval"] = request.interval
    return BacktestStrategyDefinitionResult(
        valid=True,
        result=result_dto_from_raw(raw_result),
        required_indicators=validation.required_indicators,
        primary_required_indicators=validation.primary_required_indicators,
        informative_required_indicators=validation.informative_required_indicators,
    )


def _validate_informative_payload_shape(raw, timeframes) -> None:
    if isinstance(raw, list) and len(timeframes.informative) > 1:
        raise ValueError(
            "informative_bars must be mapped by timeframe alias when multiple "
            "informative timeframes are declared"
        )


def _select_informative_bars(
    raw: list[dict] | dict[str, list[dict]] | None,
    timeframe: InformativeTimeframe,
) -> list[dict]:
    if raw is None:
        raise ValueError(f"Missing informative bars for timeframe '{timeframe.alias}'")
    if isinstance(raw, list):
        return raw
    if timeframe.alias not in raw:
        raise ValueError(f"Missing informative bars for timeframe '{timeframe.alias}'")
    return raw[timeframe.alias]


def _warmup_errors(warmup: dict) -> list[StrategyValidationError]:
    """Convert required-data warmup diagnostics into blocking errors."""
    errors: list[StrategyValidationError] = []
    if warmup.get("no_tradable_bars"):
        errors.append(
            _err(
                "$.bars",
                "No tradable bars remain after indicator/feature warmup.",
                "no_tradable_bars",
            )
        )
    missing = warmup.get("missing_after_warmup", [])
    if missing:
        errors.append(
            _err(
                "$.bars",
                "Required columns contain missing values after warmup: "
                + ", ".join(missing),
                "missing_after_warmup",
            )
        )
    return errors


def _err(path: str, message: str, code: str) -> StrategyValidationError:
    return StrategyValidationError(path=path, message=message, code=code)


_OHLCV_COLUMNS = {"open", "high", "low", "close", "volume", "timestamp"}


def _bars_are_raw(bars: list[dict], required_columns: list[str]) -> bool:
    """Return True if *bars* contain no indicator columns — they are raw OHLCV.

    Pre-enriched bars (from async indicator jobs) have indicator columns
    like ``sma_20``, ``vp_poc``, etc. Raw bars only have OHLCV columns.
    If any required non-OHLCV column is present in the first bar, the bars
    are considered pre-enriched and should use the legacy frame path.
    """
    if not bars:
        return False
    indicator_cols = [c for c in required_columns if c not in _OHLCV_COLUMNS]
    if not indicator_cols:
        # No indicator columns required — bars are effectively raw
        return True
    first = bars[0]
    return not any(c in first for c in indicator_cols)
