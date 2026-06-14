"""UnifiedMetricCatalog — single source of truth for metric names + capabilities.

Merges the parser-side IndicatorCapabilityProvider (which indicator names
the strategy YAML parser accepts) with the capability-side MarketMetricCatalog
(which metrics are computable and at what confidence).

This eliminates the name-sync gap between the two former catalogs:
StrategyIndicatorCatalog (parser) and StaticMarketMetricCatalog (capability).
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
from finbar_strategy_runtime.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
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
from finbar_strategy_runtime.parser.strategy_indicator_catalog import (
    StrategyIndicatorCatalog,
)

# ---------------------------------------------------------------------------
# Handler registry — populated by @_register in the indicator calculator.
# A metric is computable only if its name appears here AND its data class
# is satisfied. This enforces Invariant #4 (confidence honesty).
# ---------------------------------------------------------------------------

_HANDLED_NAMES: set[str] = set()


def register_handler(name: str) -> None:
    """Record that a compute handler exists for `name`.

    Called by the ``@_register`` decorator in
    ``pandas_ta_indicator_calculator``. Must be called at import time
    (module side-effect) so the catalog sees all handlers before any
    ``check()`` call.
    """
    _HANDLED_NAMES.add(name)


# ---------------------------------------------------------------------------
# UnifiedMetricCatalog
# ---------------------------------------------------------------------------


class UnifiedMetricCatalog(IndicatorCapabilityProvider, MarketMetricCatalog):
    """Merges parser whitelist + capability registry into one catalog.

    Implements:
    - ``IndicatorCapabilityProvider`` (parser-side): ``resolve``,
      ``supports_concrete``, ``accepts_period``, etc.
    - ``MarketMetricCatalog`` (capability-side): ``check``, ``resolve_best``,
      ``get``, ``list``.
    """

    def __init__(self) -> None:
        self._strategy_catalog = StrategyIndicatorCatalog()
        self._by_name: dict[str, MarketMetricDefinition] = {
            m.name: m for m in METRICS + CONCEPTUAL_METRICS
        }

    # ====================================================================
    # Parser-side: IndicatorCapabilityProvider
    # ====================================================================

    def resolve(self, indicator_type: str, period: int | None) -> str | None:
        """Resolve an indicator type/period to a concrete column name."""
        return self._strategy_catalog.resolve(indicator_type, period)

    def requires_period(self, indicator_type: str) -> bool:
        """Return True when the indicator type requires a period."""
        return self._strategy_catalog.requires_period(indicator_type)

    def accepts_period(self, indicator_type: str) -> bool:
        """Return True when the indicator type accepts a period argument."""
        return self._strategy_catalog.accepts_period(indicator_type)

    def supports_concrete(self, name: str) -> bool:
        """Return True when a concrete column is known to the catalog.

        Checks both the market-metric definitions and the legacy parser
        indicator set (parameterized names like sma_20, vp_poc_5d, etc.).
        """
        if name in self._by_name:
            return True
        return self._strategy_catalog.supports_concrete(name)

    def supported_concrete_names(self) -> list[str]:
        """Return all concrete indicator columns currently supported."""
        names = set(self._strategy_catalog.supported_concrete_names())
        names.update(self._by_name.keys())
        return sorted(names)

    def as_dict(self) -> dict:
        """Return a JSON-serializable capabilities payload."""
        return self._strategy_catalog.as_dict()

    # ====================================================================
    # Capability-side: MarketMetricCatalog
    # ====================================================================

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
        """Check whether a metric can be computed with the given data class.

        Enforces confidence honesty (Invariant #4): returns
        ``computable=True`` only when a handler is registered AND the
        data class is satisfied.
        """
        definition = self._by_name.get(name)
        if definition is not None:
            return self._check_definition(definition, available_data_class)

        # Not a market-metric definition — check if it's a parser indicator
        return self._check_parser_indicator(name)

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
            return self.check(concept, available_data_class)

        try:
            dc = DataClass(available_data_class)
        except ValueError:
            dc = DataClass.DAILY_OHLCV

        return self._select_best_path(definition, dc, interval, force_proxy)

    # ====================================================================
    # Helper for name-sync test (Scenario 1.3)
    # ====================================================================

    def all_metric_names(self) -> set[str]:
        """Return every catalogued metric name (for the name-sync test).

        Includes both market-metric definitions and legacy parser
        indicator names.
        """
        names = set(self._by_name.keys())
        names.update(self._strategy_catalog.supported_concrete_names())
        names.update(self._strategy_catalog._FIXED.keys())
        names.update(self._strategy_catalog._FIXED.values())
        return names

    # ====================================================================
    # Private helpers
    # ====================================================================

    def _check_definition(
        self,
        definition: MarketMetricDefinition,
        available_data_class: str,
    ) -> MetricCapabilityResult:
        """Check computability for a name with a MarketMetricDefinition."""
        if not definition.implemented:
            return MetricCapabilityResult(
                metric=definition.name,
                supported=True,
                computable=False,
                confidence=MetricConfidence.UNAVAILABLE,
                warnings=("Metric catalogued but not yet implemented.",),
            )

        # Confidence honesty: no handler → not computable
        if definition.name not in _HANDLED_NAMES:
            return MetricCapabilityResult(
                metric=definition.name,
                supported=True,
                computable=False,
                confidence=MetricConfidence.UNAVAILABLE,
                warnings=("No handler registered for this metric.",),
            )

        try:
            dc = DataClass(available_data_class)
        except ValueError:
            dc = DataClass.DAILY_OHLCV

        return self._check_data_class(definition, dc)

    def _check_data_class(
        self,
        definition: MarketMetricDefinition,
        available_class: DataClass,
    ) -> MetricCapabilityResult:
        """Check data-class requirements for a handled metric."""
        # External provider metrics require provider configuration
        if (
            definition.required_data_classes
            and definition.required_data_classes[0]
            == DataClass.EXTERNAL_PROVIDER
        ):
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

    def _check_parser_indicator(self, name: str) -> MetricCapabilityResult:
        """Check a name that has no MarketMetricDefinition (legacy indicator)."""
        if not self._strategy_catalog.supports_concrete(name):
            return MetricCapabilityResult(
                metric=name,
                supported=False,
                computable=False,
                confidence=MetricConfidence.UNAVAILABLE,
                warnings=("Unknown metric name.",),
            )

        if name in _HANDLED_NAMES:
            # proxy_-prefixed indicators are approximations, not actual data
            confidence = (
                MetricConfidence.PROXY
                if name.startswith("proxy_")
                else MetricConfidence.ACTUAL
            )
            return MetricCapabilityResult(
                metric=name,
                supported=True,
                computable=True,
                confidence=confidence,
                selected_metric=name,
            )

        return MetricCapabilityResult(
            metric=name,
            supported=True,
            computable=False,
            confidence=MetricConfidence.UNAVAILABLE,
            warnings=("No handler registered for this indicator.",),
        )

    def _select_best_path(
        self,
        definition: MarketMetricDefinition,
        dc: DataClass,
        interval: str,
        force_proxy: bool,
    ) -> MetricCapabilityResult:
        """Walk resolution paths by priority and select the first match."""
        paths = sorted(definition.resolution_paths, key=lambda p: p.priority)
        selected: MetricResolutionPath | None = None

        for path in paths:
            if force_proxy and path.confidence in (
                MetricConfidence.ACTUAL,
                MetricConfidence.APPROXIMATION,
            ):
                continue
            if force_proxy:
                selected = path
                break
            if path.required_data_class != dc:
                continue
            if path.interval_min and dc == DataClass.INTRADAY_OHLCV:
                if not _interval_matches(interval, path.interval_min):
                    continue
            selected = path
            break

        if selected is not None:
            return MetricCapabilityResult(
                metric=definition.name,
                supported=True,
                computable=True,
                confidence=selected.confidence,
                selected_metric=selected.metric_name,
                available_paths=definition.resolution_paths,
            )

        return MetricCapabilityResult(
            metric=definition.name,
            supported=True,
            computable=False,
            confidence=MetricConfidence.UNAVAILABLE,
            available_paths=definition.resolution_paths,
            missing_data_classes=tuple(
                p.required_data_class.value for p in paths
            ),
        )


# ---------------------------------------------------------------------------
# Auto-register all handlers.
# Importing the calculator module triggers every @_register decorator,
# which calls register_handler() above. This MUST come after register_handler
# and UnifiedMetricCatalog are defined so the deferred import inside
# _register() succeeds. Placing it at module bottom avoids a circular import.
# ---------------------------------------------------------------------------
import finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator  # noqa: E402,F401
