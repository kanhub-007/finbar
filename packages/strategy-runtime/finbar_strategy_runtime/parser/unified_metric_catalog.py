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
from finbar_strategy_runtime.parser.usable_metric_set import UsableMetricSet

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
        # Importing the calculator triggers every @_register decorator,
        # populating _INDICATOR_HANDLERS. We read it at construction time
        # so the dependency is explicit (no hidden global mutable state).
        import finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator  # noqa: F401
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            _INDICATOR_HANDLERS,
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
        self._handled_names: set[str] = set(_INDICATOR_HANDLERS.keys())
        self._usable = UsableMetricSet(
            by_name=self._by_name,
            handled_names=self._handled_names,
        )
        self._validate_consistency()

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
    # Construction-time consistency check (Design by Contract, INV-6)
    # ====================================================================

    def _validate_consistency(self) -> None:
        """Fail loud if any parser-side method diverges from ground truth.

        Ground truth is recomputed independently from ``_by_name`` ∩
        ``_handled_names`` (case-insensitively, matching the value object's
        lowercasing). For every catalogued name, the validator asserts:
          * ``_usable.contains(name)`` agrees with ground truth (catches a
            stale/mis-built usable set), AND
          * ``resolve(name, None)`` returns ``name`` iff usable (catches a
            future edit that bypasses ``_usable``), AND
          * ``supports_concrete(name)`` agrees with ground truth.

        Raises ``RuntimeError`` (NOT ``assert``) so it survives
        ``python -O``. This is the backstop that catches drift if a future
        edit bypasses ``UsableMetricSet`` — the exact bug class this catalog
        eradicates.
        """
        handled_lower = {h.lower() for h in self._handled_names}
        for name in self._by_name:
            ground_truth = name.lower() in handled_lower
            if self._usable.contains(name) != ground_truth:
                raise RuntimeError(
                    f"UnifiedMetricCatalog: UsableMetricSet.contains({name!r}) "
                    f"disagrees with ground truth (handler presence); parser "
                    f"gate is inconsistent."
                )
            resolved = self.resolve(name, None)
            if (resolved is not None) != ground_truth:
                raise RuntimeError(
                    f"UnifiedMetricCatalog.resolve({name!r}) disagrees with "
                    f"UsableMetricSet; parser gate is inconsistent."
                )
            if self.supports_concrete(name) != ground_truth:
                raise RuntimeError(
                    f"UnifiedMetricCatalog.supports_concrete({name!r}) "
                    f"disagrees with UsableMetricSet; parser gate is "
                    f"inconsistent."
                )

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

        # Confidence honesty: no handler → not computable. The usable set
        # is the authority for handler presence (INV-1).
        if not self._usable.contains(definition.name):
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

        if name in self._handled_names:
            # proxy_-prefixed indicators are approximations, not actual data.
            # This is capability-side (check): legacy parser indicators are
            # checked against the full handler set, not the registry usable
            # set (which only tracks MarketMetricDefinition entries).
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
            missing_data_classes=tuple(p.required_data_class.value for p in paths),
        )
