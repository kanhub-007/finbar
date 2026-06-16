"""Serialization helpers for metric catalog DTOs.

Shared between MCP tools and API routes to avoid coupling the API layer
to private implementation details of the MCP module.
"""

from finbar_strategy_runtime.domain.entities.market_metric_definition import (
    MarketMetricDefinition,
)
from finbar_strategy_runtime.domain.entities.metric_capability_result import (
    MetricCapabilityResult,
)
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog


def metric_to_dict(
    catalog: UnifiedMetricCatalog,
    definition: MarketMetricDefinition,
    data_class: str,
) -> dict:
    """Serialize a MarketMetricDefinition + its capability to a dict.

    Args:
        catalog: The catalog to check computability against.
        definition: The metric definition to serialize.
        data_class: Available data class string.

    Returns:
        JSON-safe dict with name, family, description, computable,
        confidence, and implemented fields.
    """
    result = catalog.check(definition.name, data_class)
    # Compose a human-readable description that includes the condition
    # note when present, so list_market_metrics surfaces the constraint
    # (spec 2026-06-16 Scenario 3 Verify checks ``description``).
    description = definition.description
    if definition.condition_note:
        description = f"{description} {definition.condition_note}"
    return {
        "name": definition.name,
        "family": definition.family.value,
        "description": description,
        "computable": result.computable,
        "confidence": result.confidence.value,
        "implemented": definition.implemented,
        "min_lookback": definition.min_lookback,
        "condition_note": definition.condition_note,
    }


def result_to_dict(result: MetricCapabilityResult) -> dict:
    """Serialize a MetricCapabilityResult to a JSON-safe dict.

    Args:
        result: The capability result to serialize.

    Returns:
        JSON-safe dict with all fields, including resolution paths.
    """
    return {
        "metric": result.metric,
        "supported": result.supported,
        "computable": result.computable,
        "confidence": result.confidence.value,
        "selected_metric": result.selected_metric,
        "missing_data_classes": list(result.missing_data_classes),
        "missing_providers": list(result.missing_providers),
        "proxy_candidates": list(result.proxy_candidates),
        "warnings": list(result.warnings),
        "available_paths": [
            {
                "metric_name": p.metric_name,
                "required_data_class": p.required_data_class.value,
                "confidence": p.confidence.value,
                "priority": p.priority,
            }
            for p in result.available_paths
        ],
    }
