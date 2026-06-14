"""MarketMetricCatalog — interface for the market metric registry."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from finbar_strategy_runtime.domain.entities.market_metric_definition import (
    MarketMetricDefinition,
)
from finbar_strategy_runtime.domain.entities.metric_capability_result import (
    MetricCapabilityResult,
)
from finbar_strategy_runtime.domain.entities.metric_family import MetricFamily


class MarketMetricCatalog(ABC):
    """Registry of all market metrics Finbar knows about.

    The catalog is the single source of truth for:
    - Which metrics exist (including those requiring unavailable data)
    - What data each metric requires
    - What confidence level applies given current data
    - What proxy candidates are available when actual metrics aren't
    """

    @abstractmethod
    def get(self, name: str) -> MarketMetricDefinition | None:
        """Return the definition for a named metric, or None."""

    @abstractmethod
    def list(
        self, family: MetricFamily | None = None
    ) -> Sequence[MarketMetricDefinition]:
        """List all definitions, optionally filtered by family."""

    @abstractmethod
    def check(
        self,
        name: str,
        available_data_class: str,
    ) -> MetricCapabilityResult:
        """Check whether a metric can be computed with the given data class.

        Returns a capability result with:
        - Whether the metric is known (supported)
        - Whether it is computable (computable)
        - The confidence level for the result
        - Proxy candidates when the metric is unavailable
        - Missing data classes / providers when not computable
        """
