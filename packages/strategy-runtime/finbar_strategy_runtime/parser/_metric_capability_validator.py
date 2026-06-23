"""MetricCapabilityValidator — capability computability + consistency checks.

Extracted from ``UnifiedMetricCatalog`` to honour Single Responsibility:
the catalog owns the metric *whitelist + metadata*; this collaborator owns
the *computability logic* (data-class checks, resolution-path selection)
and the construction-time *consistency backstop*.

The validator is constructed with the catalog's immutable state (the
by-name definitions, the handler-name set, the usable set, and a thin
resolver interface) so it can be tested in isolation.
"""

from __future__ import annotations

from finbar_strategy_runtime.domain.entities.data_class import DataClass
from finbar_strategy_runtime.domain.entities.market_metric_definition import (
    MarketMetricDefinition,
)
from finbar_strategy_runtime.domain.entities.metric_capability_result import (
    MetricCapabilityResult,
)
from finbar_strategy_runtime.domain.entities.metric_confidence import (
    MetricConfidence,
)
from finbar_strategy_runtime.domain.entities.metric_resolution_path import (
    MetricResolutionPath,
)
from finbar_strategy_runtime.parser.usable_metric_set import UsableMetricSet


class MetricCapabilityValidator:
    """Compute metric computability and validate catalog consistency."""

    def __init__(
        self,
        by_name: dict[str, MarketMetricDefinition],
        handled_names: set[str],
        usable: UsableMetricSet,
    ) -> None:
        self._by_name = by_name
        self._handled_names = handled_names
        self._usable = usable

    # ── construction-time consistency backstop (INV-6) ─────────────────

    def validate_consistency(
        self,
        resolver,
    ) -> None:
        """Fail loud if any parser-side method diverges from ground truth.

        Ground truth is recomputed independently from ``_by_name`` ∩
        ``_handled_names`` (case-insensitively). For every catalogued name
        the validator asserts:

        * ``usable.contains(name)`` agrees with ground truth, AND
        * ``resolver.resolve(name, None)`` returns ``name`` iff usable, AND
        * ``resolver.supports_concrete(name)`` agrees with ground truth.

        ``resolver`` is the catalog (passed in to avoid a circular hold);
        it must expose ``resolve(name, period)`` and ``supports_concrete(name)``.

        Raises ``RuntimeError`` (NOT ``assert``) so it survives ``python -O``.
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
            resolved = resolver.resolve(name, None)
            if (resolved is not None) != ground_truth:
                raise RuntimeError(
                    f"UnifiedMetricCatalog.resolve({name!r}) disagrees with "
                    f"UsableMetricSet; parser gate is inconsistent."
                )
            if resolver.supports_concrete(name) != ground_truth:
                raise RuntimeError(
                    f"UnifiedMetricCatalog.supports_concrete({name!r}) "
                    f"disagrees with UsableMetricSet; parser gate is "
                    f"inconsistent."
                )

    # ── capability checks (capability-side: check / resolve_best) ──────

    def check_definition(
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

        # Confidence honesty: no handler → not computable (INV-1).
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

        return self.check_data_class(definition, dc)

    def check_data_class(
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

        missing_cols = _missing_columns(definition.required_columns, available_class)
        if missing_cols:
            return MetricCapabilityResult(
                metric=definition.name,
                supported=True,
                computable=False,
                confidence=MetricConfidence.UNAVAILABLE,
                warnings=(
                    f"Requires column(s) {missing_cols} not provided by "
                    f"{available_class.value} data.",
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

    def check_parser_indicator(
        self,
        name: str,
        supports_concrete: bool,
    ) -> MetricCapabilityResult:
        """Check a name with no MarketMetricDefinition (legacy indicator)."""
        if not supports_concrete:
            return MetricCapabilityResult(
                metric=name,
                supported=False,
                computable=False,
                confidence=MetricConfidence.UNAVAILABLE,
                warnings=("Unknown metric name.",),
            )

        if name in self._handled_names:
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

    def select_best_path(
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


# These helpers are re-exported from _metric_registry for the validator's
# use (kept at module level to preserve the existing call shape).
from finbar_strategy_runtime.parser._metric_registry import (  # noqa: E402
    _interval_matches,
    _is_class_available,
    _missing_columns,
)

__all__ = ["MetricCapabilityValidator"]
