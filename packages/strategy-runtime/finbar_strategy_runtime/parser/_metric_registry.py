"""Static registry of all market metric definitions (data only).

This module holds the _METRICS and _CONCEPTUAL_METRICS lists plus the
pure helper functions used by both UnifiedMetricCatalog and
StaticMarketMetricCatalog. Extracting the data here lets the unified
catalog import it without pulling in the old class.
"""

from finbar_strategy_runtime.domain.entities.data_class import DataClass
from finbar_strategy_runtime.domain.entities.market_metric_definition import (
    MarketMetricDefinition,
)
from finbar_strategy_runtime.domain.entities.metric_confidence import MetricConfidence
from finbar_strategy_runtime.domain.entities.metric_family import MetricFamily
from finbar_strategy_runtime.domain.entities.metric_resolution_path import (
    MetricResolutionPath,
)

# ====================================================================
# Helper functions
# ====================================================================

def _is_class_available(
    required: tuple[DataClass, ...], available: DataClass
) -> bool:
    """Return True when `available` satisfies any of the `required` classes."""
    if not required:
        return True
    return available in required


#: Columns available per OHLCV data class. A metric whose ``required_columns``
#: extends beyond these cannot be computed from that data class (e.g.
#: ``first_last_hour_vol_fraction`` needs ``opening_volume``/``closing_volume``
#: which no OHLCV source provides). Used by check_metric (Scenario 2).
_AVAILABLE_COLUMNS_BY_CLASS: dict[DataClass, frozenset[str]] = {
    DataClass.DAILY_OHLCV: frozenset({"open", "high", "low", "close", "volume"}),
    DataClass.INTRADAY_OHLCV: frozenset({"open", "high", "low", "close", "volume"}),
}


def _missing_columns(
    required_columns: tuple[str, ...], available_class: DataClass
) -> list[str]:
    """Return required columns not available in the data class, sorted.

    Returns an empty list when the data class provides all required columns
    or when the data class is not OHLCV-based (external providers are
    checked separately via ``required_providers``).
    """
    available = _AVAILABLE_COLUMNS_BY_CLASS.get(available_class)
    if available is None:
        return []
    return [c for c in required_columns if c not in available]


def _interval_matches(available: str, required_min: str) -> bool:
    """Check whether the available interval is at least as fine as required.

    For intraday data, '5min' is finer than '1h'.
    For daily, only '1d' or '' matches.
    """
    if not required_min:
        return True

    def _to_minutes(interval: str) -> int:
        if interval in ("1d", "", "day"):
            return 1440
        if interval.endswith("min"):
            return int(interval.replace("min", ""))
        if interval.endswith("h"):
            return int(interval.replace("h", "")) * 60
        return 0

    return _to_minutes(available) <= _to_minutes(required_min)




from ._metric_data import METRICS  # noqa: F401 (re-export for backward compat)

# Conceptual metrics with dual-path resolution
CONCEPTUAL_METRICS: list[MarketMetricDefinition] = [
    MarketMetricDefinition(
        name="volatility",
        family=MetricFamily.VOLATILITY,
        description="Conceptual volatility — auto-selects best path.",
        resolution_paths=(
            MetricResolutionPath(
                metric_name="realized_vol_5m",
                required_data_class=DataClass.INTRADAY_OHLCV,
                required_columns=("close",),
                confidence=MetricConfidence.ACTUAL,
                priority=1,
                interval_min="5min",
            ),
            MetricResolutionPath(
                metric_name="realized_vol_1h",
                required_data_class=DataClass.INTRADAY_OHLCV,
                required_columns=("close",),
                confidence=MetricConfidence.APPROXIMATION,
                priority=2,
                interval_min="1h",
            ),
            MetricResolutionPath(
                metric_name="yang_zhang_vol",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("open", "high", "low", "close"),
                confidence=MetricConfidence.PROXY,
                priority=3,
            ),
        ),
    ),
    MarketMetricDefinition(
        name="spread",
        family=MetricFamily.SPREAD,
        description="Conceptual spread — auto-selects best path.",
        resolution_paths=(
            MetricResolutionPath(
                metric_name="fong_holden_tran_spread",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("open", "high", "low", "close"),
                confidence=MetricConfidence.PROXY,
                priority=1,
            ),
            MetricResolutionPath(
                metric_name="roll_spread",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("close",),
                confidence=MetricConfidence.PROXY,
                priority=2,
            ),
        ),
    ),
    MarketMetricDefinition(
        name="jump_detection",
        family=MetricFamily.JUMP_TAIL_RISK,
        description="Conceptual jump detection — auto-selects best path.",
        resolution_paths=(
            MetricResolutionPath(
                metric_name="bipower_variation",
                required_data_class=DataClass.INTRADAY_OHLCV,
                required_columns=("close",),
                confidence=MetricConfidence.ACTUAL,
                priority=1,
                interval_min="5min",
            ),
            MetricResolutionPath(
                metric_name="cc_rs_jump_proxy",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("high", "low"),
                confidence=MetricConfidence.PROXY,
                priority=2,
            ),
        ),
    ),
    MarketMetricDefinition(
        name="intraday_seasonality",
        family=MetricFamily.INTRADAY_SEASONALITY,
        description="Conceptual intraday seasonality — auto-selects best path.",
        resolution_paths=(
            MetricResolutionPath(
                metric_name="empirical_volume_curve",
                required_data_class=DataClass.INTRADAY_OHLCV,
                required_columns=("volume",),
                confidence=MetricConfidence.ACTUAL,
                priority=1,
                interval_min="5min",
            ),
            MetricResolutionPath(
                metric_name="parametric_u_shape",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("volume",),
                confidence=MetricConfidence.PROXY,
                priority=2,
            ),
        ),
    ),
    MarketMetricDefinition(
        name="order_flow_imbalance",
        family=MetricFamily.ORDER_FLOW,
        description="Conceptual order flow imbalance — auto-selects best path.",
        resolution_paths=(
            MetricResolutionPath(
                metric_name="bvc_ofi",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("close", "volume"),
                confidence=MetricConfidence.PROXY,
                priority=1,
            ),
        ),
    ),
    MarketMetricDefinition(
        name="price_impact",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Conceptual price impact — auto-selects best path.",
        resolution_paths=(
            MetricResolutionPath(
                metric_name="amihud_illiq",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("close", "volume"),
                confidence=MetricConfidence.PROXY,
                priority=1,
            ),
        ),
    ),
]


