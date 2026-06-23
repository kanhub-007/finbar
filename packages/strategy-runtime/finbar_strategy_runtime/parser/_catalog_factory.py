"""Default catalog factory — single source of the default catalog instance.

Resolvers require an ``IndicatorCapabilityProvider`` via Constructor Injection
(no default). The parser wires the catalog down through the resolver chain,
so resolvers no longer build their own. This module exists for the one place
that still needs a default — ``StrategyDefinitionParser`` (the composition
root for this sub-package) — and to break the import cycle with
``UnifiedMetricCatalog`` in a single location rather than six.

Usage:

    from finbar_strategy_runtime.parser._catalog_factory import default_catalog
    catalog = default_catalog()
"""

from __future__ import annotations

from finbar_strategy_runtime.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
)


def default_catalog() -> IndicatorCapabilityProvider:
    """Build the default UnifiedMetricCatalog.

    Lazy import avoids a circular import with ``UnifiedMetricCatalog``, which
    imports from this package's other parser modules.
    """
    from finbar_strategy_runtime.parser.unified_metric_catalog import (
        UnifiedMetricCatalog,
    )

    return UnifiedMetricCatalog()


__all__ = ["default_catalog"]
