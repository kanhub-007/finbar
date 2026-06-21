"""Causal prefix oracle helpers for streaming metric parity tests."""

from __future__ import annotations

import math
from typing import Any

from finbar_strategy_runtime.indicators.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)
from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
    StreamingIndicatorEngine,
)
from tests.support.metric_value_assertions import assert_equivalent_metric_value


def expected_prefix_value(metric_name: str, bars: list[dict], index: int) -> Any:
    """Return the causal prefix-oracle value for one metric at one index.

    Args:
        metric_name: Concrete metric to calculate.
        bars: Ordered OHLCV bars.
        index: Row index whose causal value is requested.

    Returns:
        The metric value from a batch calculation over ``bars[:index + 1]``.

    Raises:
        IndexError: If ``index`` is outside the bars list.
    """
    if index < 0 or index >= len(bars):
        raise IndexError(f"Prefix oracle index out of range: {index}")
    prefix = bars[: index + 1]
    frame = PandasBarFrameConverter().bars_to_frame(prefix)
    enriched = PandasTaIndicatorCalculator().calculate(frame, [metric_name])
    return enriched.iloc[-1][metric_name]


def assert_metric_matches_prefix_oracle(
    metric_name: str,
    bars: list[dict],
    sample_indices: list[int],
    *,
    rel_tol: float = 1e-9,
    abs_tol: float = 1e-12,
) -> None:
    """Assert streaming metric values match the causal prefix oracle.

    Args:
        metric_name: Concrete metric to compare.
        bars: Ordered OHLCV bars.
        sample_indices: Row indices to compare.
        rel_tol: Relative tolerance for numeric metrics.
        abs_tol: Absolute tolerance for numeric metrics.
    """
    sample_set = set(sample_indices)
    engine = StreamingIndicatorEngine(indicators=[metric_name])
    for index, bar in enumerate(bars):
        latest = engine.update(bar)
        if index not in sample_set:
            continue
        got = latest.values.get(metric_name, math.nan)
        expected = expected_prefix_value(metric_name, bars, index)
        assert_equivalent_metric_value(
            got,
            expected,
            metric_name,
            rel_tol=rel_tol,
            abs_tol=abs_tol,
        )
