"""BacktestStrategyDefinitionUseCase — run unsaved JSON strategies."""

import logging
from typing import Any

from finbar.core.application.backtest_result_mapper import result_dto_from_raw
from finbar.core.application.dto.backtest_result import BacktestResultDTO
from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
)
from finbar.core.application.dto.backtest_strategy_definition_result import (
    BacktestStrategyDefinitionResult,
)
from finbar.core.domain.entities.informative_timeframe import InformativeTimeframe
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)
from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
from finbar.core.domain.interfaces.bar_frame_converter import BarFrameConverter
from finbar.core.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.domain.interfaces.strategy_definition_strategy_factory import (
    StrategyDefinitionStrategyFactory,
)
from finbar.core.domain.interfaces.timeframe_bar_merger import TimeframeBarMerger

logger = logging.getLogger(__name__)


class BacktestStrategyDefinitionUseCase:
    """Backtest a JSON strategy against already-enriched bars.

    This use case intentionally does not fetch prices or calculate indicators.
    The MCP agent orchestrates those separate calls before invoking backtest.
    """

    def __init__(
        self,
        engine: BacktestEngine,
        converter: BarFrameConverter,
        strategy_factory: StrategyDefinitionStrategyFactory,
        parser: StrategyDefinitionParser,
        timeframe_merger: TimeframeBarMerger | None = None,
    ):
        """Create the use case with injected engine/converter/factory."""
        self._engine = engine
        self._converter = converter
        self._strategy_factory = strategy_factory
        self._parser = parser
        self._timeframe_merger = timeframe_merger

    def execute(
        self,
        request: BacktestStrategyDefinitionRequest,
    ) -> BacktestStrategyDefinitionResult:
        """Validate, verify columns, and run the supplied JSON strategy."""
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

        merged_bars = self._converter.frame_to_bars(frame)
        missing = _missing_columns(merged_bars, validation.required_columns)
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

        return _run_backtest(
            request,
            validation,
            frame,
            self._strategy_factory,
            self._engine,
        )

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


def _run_backtest(
    request: BacktestStrategyDefinitionRequest,
    validation,
    frame: Any,
    strategy_factory: StrategyDefinitionStrategyFactory,
    engine: BacktestEngine,
) -> BacktestStrategyDefinitionResult:
    strategy = strategy_factory.create(validation.definition)
    try:
        raw_result = engine.run(
            df=frame,
            strategy=strategy,
            initial_cash=request.initial_cash,
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


def _missing_columns(bars: list[dict], required: list[str]) -> list[str]:
    available: set[str] = set()
    for bar in bars:
        available.update(bar.keys())
    return [column for column in required if column not in available]


def _err(path: str, message: str, code: str) -> StrategyValidationError:
    return StrategyValidationError(path=path, message=message, code=code)
