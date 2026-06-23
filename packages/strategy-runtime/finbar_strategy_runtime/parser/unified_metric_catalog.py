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
    _missing_columns,
)
from finbar_strategy_runtime.parser.strategy_indicator_catalog import (
    StrategyIndicatorCatalog,
)
from finbar_strategy_runtime.parser._metric_capability_validator import (
    MetricCapabilityValidator,
)
from finbar_strategy_runtime.parser.usable_metric_set import UsableMetricSet

# ---------------------------------------------------------------------------
# UnifiedMetricCatalog
# ---------------------------------------------------------------------------

#: Columns always present in any OHLCV frame. A handler ``requires`` set
#: that extends beyond these denotes a dependency on another indicator
#: that must be computed in the same batch (e.g. ``atr``, ``vp_poc``).
#: ``check_metric`` warns about these so users co-request them instead of
#: getting silent NaN (spec 2026-06-16 Scenario 5).
_OHLCV_COLUMNS = frozenset({"open", "high", "low", "close", "volume"})


def _non_ohlcv_requires(handled_names: set[str], name: str) -> list[str]:
    """Return the non-OHLCV columns a metric's handler requires, sorted.

    Returns an empty list for unknown names or handlers requiring only
    OHLCV columns.
    """
    from finbar_strategy_runtime.indicators._handler_registry import (
        default_handler_registry,
    )

    entry = default_handler_registry().get(name)
    if entry is None:
        return []
    _handler, requires = entry
    return sorted(requires - _OHLCV_COLUMNS)


class UnifiedMetricCatalog(IndicatorCapabilityProvider, MarketMetricCatalog):
    """Merges parser whitelist + capability registry into one catalog.

    Implements:
    - ``IndicatorCapabilityProvider`` (parser-side): ``resolve``,
      ``supports_concrete``, ``accepts_period``, etc.
    - ``MarketMetricCatalog`` (capability-side): ``check``, ``resolve_best``,
      ``get``, ``list``.
    """

    def __init__(self, handler_registry: "HandlerRegistry | None" = None) -> None:
        self._strategy_catalog = StrategyIndicatorCatalog()
        self._by_name: dict[str, MarketMetricDefinition] = {
            m.name: m for m in METRICS + CONCEPTUAL_METRICS
        }
        # The handler registry is injected (tests may pass a stub). The
        # default factory imports the handlers package so every
        # ``@_register`` decorator has run, then returns the populated
        # registry — no hidden global mutable state at the call site.
        from finbar_strategy_runtime.indicators._handler_registry import (
            HandlerRegistry,
            default_handler_registry,
        )

        self._handlers: HandlerRegistry = (
            handler_registry or default_handler_registry()
        )

        # The parser-side usable-set rule lives in ONE place: this value
        # object. Parser methods (resolve / supports_concrete /
        # supported_concrete_names / as_dict) MUST go through ``_usable``
        # and never read ``_by_name`` / handler keys directly — that
        # duplication was the drift cause of the original resolve() bug.
        # ``_by_name`` and ``_handled_names`` are retained ONLY for the
        # capability-side methods (get / list / check, which answer
        # metadata) and the construction-time consistency check (ground
        # truth). They are NOT consulted by parser-side resolution.
        self._handled_names: set[str] = self._handlers.names()
        self._usable = UsableMetricSet(
            by_name=self._by_name,
            handled_names=self._handled_names,
        )
        self._validator = MetricCapabilityValidator(
            by_name=self._by_name,
            handled_names=self._handled_names,
            usable=self._usable,
        )
        self._validator.validate_consistency(self)

    # ====================================================================
    # Parser-side: IndicatorCapabilityProvider
    # ====================================================================

    def resolve(self, indicator_type: str, period: int | None) -> str | None:
        """Resolve an indicator type/period to a concrete column name.

        Registry (catalogued) metrics take no period: when ``period`` is
        None, the usable set is the single source of truth (INV-1). Names
        the registry does not know — period-parameterised indicators and
        rolling-VP patterns — fall through to the legacy catalog (INV-4).
        """
        name = indicator_type.lower()
        if period is None:
            usable = self._usable.resolve(name)
            if usable is not None:
                return usable
        return self._strategy_catalog.resolve(indicator_type, period)

    def requires_period(self, indicator_type: str) -> bool:
        """Return True when the indicator type requires a period."""
        return self._strategy_catalog.requires_period(indicator_type)

    def accepts_period(self, indicator_type: str) -> bool:
        """Return True when the indicator type accepts a period argument."""
        return self._strategy_catalog.accepts_period(indicator_type)

    def supports_concrete(self, name: str) -> bool:
        """Return True when a concrete column is usable in a strategy.

        For registry (catalogued) names the usable set is the single
        source of truth (INV-1, INV-2): a catalogued metric is accepted
        iff it has a registered handler. Catalogued-but-unimplemented
        metrics (Elliott Wave, turnover, VIX, etc.) are discoverable via
        ``list_market_metrics`` / ``check_metric`` but rejected by the
        parser. Parameterised/dynamic names (sma_50, vp_poc_10d, etc.)
        are delegated to the legacy strategy catalog.

        Case-insensitive, mirroring ``resolve()`` (INV-3): a non-lowercase
        name (e.g. ``"BAG_HOLDING"``) is accepted iff its lowercased form
        is usable. Without this, ``resolve`` and ``supports_concrete``
        disagreed for mixed-case inputs (the operand parser passes
        un-lowercased condition operands).
        """
        key = name.lower()
        if key in self._by_name:
            return self._usable.contains(key)
        return self._strategy_catalog.supports_concrete(key)

    def supported_concrete_names(self) -> list[str]:
        """Return all concrete indicator columns currently supported.

        Combines the legacy fixed/period/pattern names with the registry
        usable set (catalogued metrics that have registered handlers).
        """
        names = set(self._strategy_catalog.supported_concrete_names())
        names.update(self._usable.names())
        return sorted(names)

    def as_dict(self) -> dict:
        """Return a JSON-serializable capabilities payload.

        The ``fixed_indicators`` list surfaces every catalogued metric
        that has a registered handler (the usable set), in addition to
        the legacy fixed indicators.
        """
        payload = self._strategy_catalog.as_dict()
        payload["fixed_indicators"] = sorted(
            set(payload.get("fixed_indicators", [])) | self._usable.names()
        )
        return payload

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
        data class is satisfied. Also warns about non-OHLCV handler
        dependencies (Scenario 5): a metric requiring e.g. ``atr`` will
        silently produce NaN unless that dependency is computed in the
        same batch.
        """
        definition = self._by_name.get(name)
        if definition is not None:
            return self._add_dependency_warning(
                self._validator.check_definition(definition, available_data_class), name
            )

        # Not a market-metric definition — check if it's a parser indicator
        return self._add_dependency_warning(
            self._validator.check_parser_indicator(
                name, self._strategy_catalog.supports_concrete(name)
            ),
            name,
        )

    def _add_dependency_warning(
        self, result: MetricCapabilityResult, name: str
    ) -> MetricCapabilityResult:
        """Append a warning for non-OHLCV handler dependencies (Scenario 5)."""
        deps = _non_ohlcv_requires(self._handled_names, name)
        if not deps:
            return result
        warning = (
            f"Requires indicator column(s) {deps} to be computed in the "
            f"same batch; this metric returns NaN otherwise."
        )
        return MetricCapabilityResult(
            metric=result.metric,
            supported=result.supported,
            computable=result.computable,
            confidence=result.confidence,
            selected_metric=result.selected_metric,
            available_paths=result.available_paths,
            missing_data_classes=result.missing_data_classes,
            missing_providers=result.missing_providers,
            proxy_candidates=result.proxy_candidates,
            warnings=(*result.warnings, warning),
        )

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

        return self._validator.select_best_path(definition, dc, interval, force_proxy)

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

    def _validate_consistency(self) -> None:
        """Re-run the construction-time consistency backstop.

        Thin delegator over :meth:`MetricCapabilityValidator.validate_consistency`.
        Kept so tests and diagnostics can re-check consistency after
        monkeypatching parser-side methods.
        """
        self._validator.validate_consistency(self)
