"""Aggregator for market metric definitions (data only).

The flat ``METRICS`` list is assembled from per-family-group shards
(``_metric_data_<group>.py``) so no single file exceeds the 500-line
review threshold. Importers should continue to import ``METRICS`` from
here (or from ``_metric_registry``, which re-exports it).
"""

from finbar_strategy_runtime.domain.entities.market_metric_definition import (
    MarketMetricDefinition,
)
from finbar_strategy_runtime.parser._metric_data_derivatives import (
    METRICS as _DERIVATIVES,
)
from finbar_strategy_runtime.parser._metric_data_microstructure import (
    METRICS as _MICROSTRUCTURE,
)
from finbar_strategy_runtime.parser._metric_data_price_action import (
    METRICS as _PRICE_ACTION,
)
from finbar_strategy_runtime.parser._metric_data_spread import METRICS as _SPREAD
from finbar_strategy_runtime.parser._metric_data_volatility_proxy import (
    METRICS as _VOLATILITY_PROXY,
)

METRICS: list[MarketMetricDefinition] = [
    *_SPREAD,
    *_VOLATILITY_PROXY,
    *_MICROSTRUCTURE,
    *_PRICE_ACTION,
    *_DERIVATIVES,
]

__all__ = ["METRICS"]
