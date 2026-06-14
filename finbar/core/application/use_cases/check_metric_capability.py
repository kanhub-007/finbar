"""CheckMetricCapabilityUseCase — can a metric be computed for a symbol?

For derivatives metrics, consults the repository to check if data was
fetched and persisted. For OHLCV metrics, delegates to the unified
catalog's ``check()`` method.
"""

from finbar.core.domain.interfaces.derivatives_repository import DerivativesRepository
from finbar_strategy_runtime.domain.entities.metric_capability_result import (
    MetricCapabilityResult,
)
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog


class CheckMetricCapabilityUseCase:
    """Check metric computability, consulting the DB for derivatives metrics.

    Enforces Invariant #6: a derivatives metric is computable only if
    its data was fetched and stored.
    """

    def __init__(self, repository: DerivativesRepository | None = None) -> None:
        """Create the use case.

        Args:
            repository: Optional derivatives repository. If None,
                derivatives metrics always report computable=False.
        """
        self._repository = repository
        self._catalog = UnifiedMetricCatalog()

    def execute(
        self,
        name: str,
        symbol: str = "",
        data_class: str = "daily_ohlcv",
    ) -> MetricCapabilityResult:
        """Check whether a metric can be computed for the given symbol.

        Args:
            name: The metric name.
            symbol: Asset symbol (used for derivatives repository lookup).
            data_class: Available data class.

        Returns:
            MetricCapabilityResult with honest computability.
        """
        result = self._catalog.check(name, data_class)

        definition = self._catalog.get(name)
        if (
            self._repository
            and definition
            and definition.family.value == "derivatives"
        ):
            rows = self._repository.find(symbol=symbol)
            if not rows:
                return MetricCapabilityResult(
                    metric=name,
                    supported=True,
                    computable=False,
                    warnings=(
                        "No derivatives data found. "
                        "Run fetch_derivatives first to populate this metric.",
                    ),
                )
        return result
