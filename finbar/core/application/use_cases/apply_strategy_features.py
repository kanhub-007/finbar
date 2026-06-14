"""ApplyStrategyFeaturesUseCase — calculate derived feature columns."""

import logging

from finbar.core.application.dto.apply_strategy_features_request import (
    ApplyStrategyFeaturesRequest,
)
from finbar.core.application.dto.apply_strategy_features_result import (
    ApplyStrategyFeaturesResult,
)
from finbar_strategy_runtime.parser.feature_input_column_collector import (
    FeatureInputColumnCollector,
)
from finbar_strategy_runtime.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar_strategy_runtime.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)
from finbar_strategy_runtime.domain.interfaces.bar_frame_converter import BarFrameConverter
from finbar_strategy_runtime.domain.interfaces.strategy_feature_calculator import (
    StrategyFeatureCalculator,
)

logger = logging.getLogger(__name__)


class ApplyStrategyFeaturesUseCase:
    """Apply features declared in a strategy definition to supplied bars."""

    def __init__(
        self,
        converter: BarFrameConverter,
        feature_calculator: StrategyFeatureCalculator,
        parser: StrategyDefinitionParser,
    ):
        """Create the use case with injected dependencies."""
        self._converter = converter
        self._feature_calculator = feature_calculator
        self._parser = parser

    def execute(
        self, request: ApplyStrategyFeaturesRequest
    ) -> ApplyStrategyFeaturesResult:
        """Validate the strategy and calculate declared feature columns."""
        if not request.bars:
            return ApplyStrategyFeaturesResult(error="No bars provided")
        validation = self._parser.parse(request.definition, request.params)
        if not validation.valid or validation.definition is None:
            return ApplyStrategyFeaturesResult(
                errors=validation.errors,
                error="Strategy definition is invalid",
            )
        if not validation.definition.features:
            return ApplyStrategyFeaturesResult(
                bars=list(request.bars),
                bar_count=len(request.bars),
            )
        required_inputs = FeatureInputColumnCollector().collect(
            validation.definition.features
        )
        missing_sources = _missing_columns(request.bars, required_inputs)
        if missing_sources:
            return ApplyStrategyFeaturesResult(
                errors=[
                    _err(
                        "$.bars",
                        "Missing feature source columns: " + ", ".join(missing_sources),
                    )
                ],
                error="Missing feature source columns: " + ", ".join(missing_sources),
            )
        try:
            frame = self._converter.bars_to_frame(request.bars)
            enriched = self._feature_calculator.calculate(
                frame, validation.definition.features
            )
            bars = self._converter.frame_to_bars(enriched)
        except Exception as exc:
            logger.exception("Strategy feature calculation failed")
            return ApplyStrategyFeaturesResult(
                error=f"Feature calculation error: {exc}"
            )
        return ApplyStrategyFeaturesResult(
            bars=bars,
            features_applied=[
                feature.name for feature in validation.definition.features
            ],
            bar_count=len(bars),
        )


def _missing_columns(bars: list[dict], required_columns: list[str]) -> list[str]:
    available: set[str] = set()
    for bar in bars:
        available.update(bar.keys())
    return [column for column in required_columns if column not in available]


def _err(path: str, message: str) -> StrategyValidationError:
    return StrategyValidationError(path=path, message=message, code="missing_columns")
