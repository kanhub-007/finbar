"""PandasStrategyFeatureCalculator — calculate v2 strategy derived features."""

from collections.abc import Callable

import pandas as pd

from finbar.core.domain.entities.feature_spec import FeatureSpec
from finbar.core.domain.interfaces.strategy_feature_calculator import (
    StrategyFeatureCalculator,
)

FeatureHandler = Callable[[pd.DataFrame, FeatureSpec], pd.Series]


class PandasStrategyFeatureCalculator(StrategyFeatureCalculator):
    """Calculate derived feature columns on pandas DataFrames."""

    def calculate(
        self, frame: pd.DataFrame, features: list[FeatureSpec]
    ) -> pd.DataFrame:
        """Return a copy of the frame with requested feature columns added."""
        result = frame.copy()
        for feature in features:
            result[feature.name] = _calculate_feature(result, feature)
        return result


def _calculate_feature(frame: pd.DataFrame, feature: FeatureSpec) -> pd.Series:
    handler = _FEATURE_HANDLERS.get(feature.type)
    if handler is None:
        return pd.Series(index=frame.index, dtype="float64")
    series = handler(frame, feature)
    if feature.shift > 0:
        series = series.shift(feature.shift)
    return series


def _rolling_max(frame: pd.DataFrame, feature: FeatureSpec) -> pd.Series:
    return frame[feature.source].rolling(window=feature.window).max()


def _rolling_min(frame: pd.DataFrame, feature: FeatureSpec) -> pd.Series:
    return frame[feature.source].rolling(window=feature.window).min()


def _rolling_mean(frame: pd.DataFrame, feature: FeatureSpec) -> pd.Series:
    return frame[feature.source].rolling(window=feature.window).mean()


def _rolling_std(frame: pd.DataFrame, feature: FeatureSpec) -> pd.Series:
    return frame[feature.source].rolling(window=feature.window).std()


def _shift(frame: pd.DataFrame, feature: FeatureSpec) -> pd.Series:
    return frame[feature.source]


def _body_pct(frame: pd.DataFrame, _feature: FeatureSpec) -> pd.Series:
    return (frame["close"] - frame["open"]).abs() / _safe_range(frame)


def _range_pct(frame: pd.DataFrame, _feature: FeatureSpec) -> pd.Series:
    return (frame["high"] - frame["low"]) / frame["close"].replace(0, pd.NA)


def _typical_price(frame: pd.DataFrame, _feature: FeatureSpec) -> pd.Series:
    return (frame["high"] + frame["low"] + frame["close"]) / 3


def _ohlc4(frame: pd.DataFrame, _feature: FeatureSpec) -> pd.Series:
    return (frame["open"] + frame["high"] + frame["low"] + frame["close"]) / 4


def _safe_range(frame: pd.DataFrame) -> pd.Series:
    return (frame["high"] - frame["low"]).replace(0, pd.NA)


_FEATURE_HANDLERS: dict[str, FeatureHandler] = {
    "rolling_max": _rolling_max,
    "rolling_min": _rolling_min,
    "rolling_mean": _rolling_mean,
    "rolling_std": _rolling_std,
    "shift": _shift,
    "body_pct": _body_pct,
    "range_pct": _range_pct,
    "typical_price": _typical_price,
    "ohlc4": _ohlc4,
}
