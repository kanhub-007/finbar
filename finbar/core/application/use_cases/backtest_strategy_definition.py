"""BacktestStrategyDefinitionUseCase — run unsaved v2 JSON strategies."""

import logging

from finbar.core.application.backtest_result_mapper import result_dto_from_raw
from finbar.core.application.dto.backtest_result import BacktestResultDTO
from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
)
from finbar.core.application.dto.backtest_strategy_definition_result import (
    BacktestStrategyDefinitionResult,
)
from finbar.core.application.services.strategy_definition_v2_parser import (
    StrategyDefinitionV2Parser,
)
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)
from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
from finbar.core.domain.interfaces.bar_frame_converter import BarFrameConverter
from finbar.core.domain.interfaces.strategy_definition_strategy_factory import (
    StrategyDefinitionStrategyFactory,
)

logger = logging.getLogger(__name__)


class BacktestStrategyDefinitionUseCase:
    """Backtest a v2 JSON strategy against already-enriched bars.

    This use case intentionally does not fetch prices or calculate indicators.
    The MCP agent orchestrates those separate calls before invoking backtest.
    """

    def __init__(
        self,
        engine: BacktestEngine,
        converter: BarFrameConverter,
        strategy_factory: StrategyDefinitionStrategyFactory,
        parser: StrategyDefinitionV2Parser | None = None,
    ):
        """Create the use case with injected engine/converter/factory."""
        self._engine = engine
        self._converter = converter
        self._strategy_factory = strategy_factory
        self._parser = parser or StrategyDefinitionV2Parser()

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
            )

        missing = _missing_columns(request.bars, validation.required_columns)
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
                missing_columns=missing,
            )

        strategy = self._strategy_factory.create(validation.definition)
        try:
            frame = self._converter.bars_to_frame(request.bars)
        except Exception as exc:
            logger.warning("Failed to convert bars: %s", exc)
            return BacktestStrategyDefinitionResult(
                valid=False,
                errors=[_err("$.bars", f"Invalid bar data: {exc}", "invalid_bars")],
                required_indicators=validation.required_indicators,
            )

        try:
            raw_result = self._engine.run(
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
            )

        raw_result["symbol"] = request.symbol
        raw_result["interval"] = request.interval
        return BacktestStrategyDefinitionResult(
            valid=True,
            result=result_dto_from_raw(raw_result),
            required_indicators=validation.required_indicators,
        )


def _missing_columns(bars: list[dict], required: list[str]) -> list[str]:
    available: set[str] = set()
    for bar in bars:
        available.update(bar.keys())
    return [column for column in required if column not in available]


def _err(path: str, message: str, code: str) -> StrategyValidationError:
    return StrategyValidationError(path=path, message=message, code=code)
