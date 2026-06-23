"""MetricResolutionPath — one computation path for a conceptual metric."""

from dataclasses import dataclass

from finbar_strategy_runtime.domain.entities.data_class import DataClass
from finbar_strategy_runtime.domain.entities.metric_confidence import MetricConfidence


@dataclass(frozen=True)
class MetricResolutionPath:
    """A single computation path for a metric, ordered by desirability.

    Conceptual metrics like 'volatility' have multiple paths:
      priority=1 → realized_vol_5m (intraday, actual)
      priority=2 → realized_vol_1h (intraday, approximation)
      priority=3 → yang_zhang_vol (daily, proxy)
    """

    metric_name: str
    required_data_class: DataClass
    required_columns: tuple[str, ...] = ()
    confidence: MetricConfidence = MetricConfidence.PROXY
    priority: int = 1
    interval_min: str = ""
