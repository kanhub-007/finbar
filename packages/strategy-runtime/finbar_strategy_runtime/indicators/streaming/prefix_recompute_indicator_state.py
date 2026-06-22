"""PrefixRecomputeIndicatorState — correctness-first causal fallback state."""

from __future__ import annotations

import math
from typing import Any

from finbar_strategy_runtime.indicators.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)

_PREFIX_RECOMPUTE_VP_NAMES = frozenset(
    {
        *(
            f"cvp_{part}_{window}d"
            for part in ("poc", "vah", "val")
            for window in (5, 10, 20)
        ),
        *(
            f"vp_{part}_{window}d"
            for part in ("poc", "vah", "val")
            for window in (5, 20)
        ),
    }
)
_PREFIX_RECOMPUTE_NAMES = frozenset(
    {
        "daily_vpin",
        "intraday_volume_curve",
        "empirical_volume_curve",
        "cumulative_signed_volume_ofi",
        "daily_return_kurtosis",
        "daily_return_skewness",
        "realized_vol_5m",
        "hurst_exponent",
        "bipower_variation",
        "realized_kurtosis",
        "realized_skewness",
        "return_volume_correlation",
        "market_regime",
        "fractal_regime",
        "day_type_classification",
        "breakout_quality",
        "breakout_signal",
        "premium_discount_zone",
        "price_vs_sma20",
        "balance_status",
        "alligator_jaw",
        "alligator_teeth",
        "alligator_lips",
        "proxy_atr",
        "proxy_iv",
        "proxy_expected_move",
        "parametric_u_shape",
        "profile_shape",
        "is_b_shape",
        "is_neutral_shape",
    }
)


class PrefixRecomputeIndicatorState:
    """Causal prefix recompute state for dependency-heavy metrics.

    The state stores all bars seen so far and recomputes the requested metric on
    the causal prefix, returning the latest-row value. It is intentionally a
    correctness-first fallback for metrics whose batch handler has transitive
    dependencies or session-count semantics that a small bounded window cannot
    satisfy.
    """

    def __init__(self, name: str) -> None:
        """Initialise the state for one metric name.

        Args:
            name: Concrete metric name to recompute on the causal prefix.
        """
        self._name = name
        self._bars: list[dict] = []
        self._current: Any = math.nan
        self._converter = PandasBarFrameConverter()
        self._calculator = PandasTaIndicatorCalculator()

    def update(self, bar: dict) -> Any:
        """Ingest one bar and return the latest prefix-recomputed value."""
        self._bars.append(bar)
        if len(self._bars) < 2:
            self._current = math.nan
            return self._current
        frame = self._converter.bars_to_frame(self._bars)
        enriched = self._calculator.calculate(frame, [self._name])
        if self._name not in enriched.columns:
            self._current = math.nan
            return self._current
        self._current = enriched[self._name].iloc[-1]
        return self._current

    def reset(self) -> None:
        """Clear accumulated prefix state."""
        self._bars.clear()
        self._current = math.nan

    @property
    def value(self) -> Any:
        """Most recently computed value."""
        return self._current


def is_prefix_recompute_metric(name: str) -> bool:
    """Return True for metrics needing correctness-first prefix state."""
    return name in _PREFIX_RECOMPUTE_NAMES or is_prefix_recompute_vp_metric(name)


def is_prefix_recompute_vp_metric(name: str) -> bool:
    """Return True for composite or multi-day VP metrics needing prefix state."""
    return name in _PREFIX_RECOMPUTE_VP_NAMES
