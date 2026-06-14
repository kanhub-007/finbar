"""StaticMarketMetricCatalog — exhaustive static registry of ~160 market metrics.

Data lists and helpers now live in _metric_registry.py.
This class is retained for backward compatibility; new code should use
UnifiedMetricCatalog instead.
"""

from collections.abc import Sequence

from finbar_strategy_runtime.domain.entities.data_class import DataClass
from finbar_strategy_runtime.domain.entities.market_metric_definition import (
    MarketMetricDefinition,
)
from finbar_strategy_runtime.domain.entities.metric_capability_result import (
    MetricCapabilityResult,
)
from finbar_strategy_runtime.domain.entities.metric_confidence import MetricConfidence
from finbar_strategy_runtime.domain.entities.metric_family import MetricFamily
from finbar_strategy_runtime.domain.entities.metric_resolution_path import (
    MetricResolutionPath,
)
from finbar_strategy_runtime.domain.interfaces.market_metric_catalog import (
    MarketMetricCatalog,
)
from finbar_strategy_runtime.parser._metric_registry import (
    CONCEPTUAL_METRICS,
    METRICS,
    _interval_matches,
    _is_class_available,
)


def _make_result(
    definition: MarketMetricDefinition,
    available_class: DataClass,
) -> MetricCapabilityResult:
    """Build a MetricCapabilityResult from a definition and available data class."""
    if not definition.implemented:
        return MetricCapabilityResult(
            metric=definition.name,
            supported=True,
            computable=False,
            confidence=MetricConfidence.UNAVAILABLE,
            warnings=("Metric catalogued but not yet implemented.",),
        )
    # External provider metrics always require provider configuration
    if definition.required_data_classes and definition.required_data_classes[0] == DataClass.EXTERNAL_PROVIDER:
        return MetricCapabilityResult(
            metric=definition.name,
            supported=True,
            computable=False,
            confidence=MetricConfidence.UNAVAILABLE,
            missing_providers=definition.required_providers,
        )
    if not _is_class_available(definition.required_data_classes, available_class):
        return MetricCapabilityResult(
            metric=definition.name,
            supported=True,
            computable=False,
            confidence=MetricConfidence.UNAVAILABLE,
            missing_data_classes=tuple(
                dc.value for dc in definition.required_data_classes
            ),
            missing_providers=definition.required_providers,
            proxy_candidates=definition.proxy_candidates,
        )

    return MetricCapabilityResult(
        metric=definition.name,
        supported=True,
        computable=True,
        confidence=definition.confidence,
        selected_metric=definition.name,
    )



# Backward-compat aliases (data now in _metric_registry)
_METRICS = METRICS
_CONCEPTUAL_METRICS = CONCEPTUAL_METRICS

class StaticMarketMetricCatalog(MarketMetricCatalog):
    """Exhaustive static catalog of ~160 market metrics.

    Implementation of MarketMetricCatalog backed by an in-memory list.
    No I/O — pure domain logic.
    """

    def __init__(self) -> None:
        self._by_name: dict[str, MarketMetricDefinition] = {
            m.name: m for m in _METRICS + _CONCEPTUAL_METRICS
        }

    def get(self, name: str) -> MarketMetricDefinition | None:
        """Return the definition for a named metric, or None."""
        return self._by_name.get(name)

    def list(
        self, family: MetricFamily | None = None
    ) -> Sequence[MarketMetricDefinition]:
        """List all definitions, optionally filtered by family."""
        if family is None:
            return tuple(self._by_name.values())
        return tuple(m for m in self._by_name.values() if m.family == family)

    def check(
        self,
        name: str,
        available_data_class: str,
    ) -> MetricCapabilityResult:
        """Check whether a metric can be computed with the given data class."""
        definition = self._by_name.get(name)
        if definition is None:
            return MetricCapabilityResult(
                metric=name,
                supported=False,
                computable=False,
                confidence=MetricConfidence.UNAVAILABLE,
                warnings=("Unknown metric name.",),
            )

        try:
            dc = DataClass(available_data_class)
        except ValueError:
            dc = DataClass.DAILY_OHLCV

        return _make_result(definition, dc)

    def resolve_best(
        self,
        concept: str,
        available_data_class: str,
        interval: str = "1d",
        force_proxy: bool = False,
    ) -> MetricCapabilityResult:
        """Auto-select the best computation path for a conceptual metric."""
        definition = self._by_name.get(concept)
        if definition is None:
            return MetricCapabilityResult(
                metric=concept,
                supported=False,
                computable=False,
                confidence=MetricConfidence.UNAVAILABLE,
                warnings=("Unknown concept name.",),
            )

        if not definition.resolution_paths:
            # No resolution paths — fall back to simple check
            return self.check(concept, available_data_class)

        try:
            dc = DataClass(available_data_class)
        except ValueError:
            dc = DataClass.DAILY_OHLCV

        paths = sorted(definition.resolution_paths, key=lambda p: p.priority)

        selected: MetricResolutionPath | None = None

        for path in paths:
            if force_proxy and path.confidence in (
                MetricConfidence.ACTUAL,
                MetricConfidence.APPROXIMATION,
            ):
                continue

            # When forcing proxy, accept any PROXY path regardless of data class
            if force_proxy:
                selected = path
                break

            if path.required_data_class != dc:
                continue

            # Interval check for intraday paths
            if path.interval_min and dc == DataClass.INTRADAY_OHLCV:
                if not _interval_matches(interval, path.interval_min):
                    continue

            selected = path
            break

        if selected is not None:
            return MetricCapabilityResult(
                metric=concept,
                supported=True,
                computable=True,
                confidence=selected.confidence,
                selected_metric=selected.metric_name,
                available_paths=definition.resolution_paths,
            )

        # No path matched — try to report which paths exist
        return MetricCapabilityResult(
            metric=concept,
            supported=True,
            computable=False,
            confidence=MetricConfidence.UNAVAILABLE,
            available_paths=definition.resolution_paths,
            missing_data_classes=tuple(
                p.required_data_class.value for p in paths
            ),
        )
