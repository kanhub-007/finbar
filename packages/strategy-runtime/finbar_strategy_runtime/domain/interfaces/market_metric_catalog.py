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
        """Check whether a metric can be computed with the given data class."""

    @abstractmethod
    def resolve_best(
        self,
        concept: str,
        available_data_class: str,
        interval: str = "1d",
        force_proxy: bool = False,
    ) -> MetricCapabilityResult:
        """Auto-select the best computation path for a conceptual metric.

        For conceptual metrics like 'volatility' that have multiple
        resolution paths (intraday actual, daily proxy), this selects
        the highest-confidence path whose data requirements are satisfied.

        Args:
            concept: Conceptual metric name (e.g. 'volatility', 'spread').
            available_data_class: The data class available.
            interval: Bar interval (e.g. '5min', '1h', '1d').
            force_proxy: If True, skip 'actual' and 'approximation' paths.

        Returns:
            MetricCapabilityResult with the best selected path.
        """
