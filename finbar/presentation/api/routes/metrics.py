"""Metric catalog API endpoints — discovery and capability checks."""

import json

from fastapi import APIRouter, Query

from finbar.presentation.mcp.tools.metrics_catalog import (
    _metric_to_dict,
    _result_to_dict,
)
from finbar_strategy_runtime.domain.entities.metric_family import MetricFamily
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])

_catalog = UnifiedMetricCatalog()


@router.get("", summary="List all market metrics")
async def list_market_metrics(
    interval: str = Query("1d", description="Bar interval"),
    family: str | None = Query(None, description="Filter by MetricFamily"),
) -> list[dict]:
    """List all catalogued metrics with computability status."""
    data_class = "intraday_ohlcv" if interval not in ("1d", "1w") else "daily_ohlcv"
    family_enum = None
    if family:
        try:
            family_enum = MetricFamily(family)
        except ValueError:
            pass
    items = _catalog.list(family_enum)
    return [_metric_to_dict(_catalog, m, data_class) for m in items]


@router.get("/check/{name}", summary="Check metric capability")
async def check_metric(
    name: str,
    data_class: str = Query("daily_ohlcv", description="Available data class"),
) -> dict:
    """Check whether a single metric is computable."""
    result = _catalog.check(name, data_class)
    return _result_to_dict(result)


@router.get("/resolve/{concept}", summary="Resolve a conceptual metric")
async def resolve_metric(
    concept: str,
    data_class: str = Query(..., description="Available data class"),
    interval: str = Query("1d", description="Bar interval"),
    force_proxy: bool = Query(False, description="Skip actual/approximation"),
) -> dict:
    """Dual-path resolution for a conceptual metric."""
    result = _catalog.resolve_best(concept, data_class, interval, force_proxy)
    return _result_to_dict(result)
