"""Indicator/calculator factories — Pandas TA, bar converters, signal calc."""

from finbar_strategy_runtime.indicators.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar_strategy_runtime.indicators.pandas_formula_feature_calculator import (
    PandasFormulaFeatureCalculator,
)
from finbar_strategy_runtime.indicators.pandas_strategy_feature_calculator import (
    PandasStrategyFeatureCalculator,
)
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)
from finbar_strategy_runtime.indicators.pandas_timeframe_bar_merger import (
    PandasTimeframeBarMerger,
)

from finbar.core.application.use_cases.apply_indicators import (
    ApplyIndicatorsUseCase,
)

_indicator_calc: PandasTaIndicatorCalculator | None = None
_bar_frame_converter: PandasBarFrameConverter | None = None
_strategy_feature_calculator: PandasStrategyFeatureCalculator | None = None
_timeframe_bar_merger: PandasTimeframeBarMerger | None = None


def get_indicator_calculator() -> PandasTaIndicatorCalculator:
    """Return the shared indicator calculator instance."""
    global _indicator_calc
    if _indicator_calc is None:
        _indicator_calc = PandasTaIndicatorCalculator()
    return _indicator_calc


def get_bar_frame_converter() -> PandasBarFrameConverter:
    """Return the shared bar-frame converter instance."""
    global _bar_frame_converter
    if _bar_frame_converter is None:
        _bar_frame_converter = PandasBarFrameConverter()
    return _bar_frame_converter


def get_strategy_feature_calculator() -> PandasStrategyFeatureCalculator:
    """Return the shared strategy feature calculator."""
    global _strategy_feature_calculator
    if _strategy_feature_calculator is None:
        _strategy_feature_calculator = PandasStrategyFeatureCalculator(
            formula_calculator=PandasFormulaFeatureCalculator(),
        )
    return _strategy_feature_calculator


def get_timeframe_bar_merger() -> PandasTimeframeBarMerger:
    """Return the shared timeframe bar merger."""
    global _timeframe_bar_merger
    if _timeframe_bar_merger is None:
        _timeframe_bar_merger = PandasTimeframeBarMerger()
    return _timeframe_bar_merger


def make_apply_indicators_use_case() -> ApplyIndicatorsUseCase:
    """Lazy-init the ApplyIndicatorsUseCase with PandasTaIndicatorCalculator."""
    return ApplyIndicatorsUseCase(
        get_indicator_calculator(),
        get_bar_frame_converter(),
    )
