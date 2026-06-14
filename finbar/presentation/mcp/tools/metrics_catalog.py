"""MCP tools exposing the unified metric catalog.

Provides three discovery tools:
- ``list_market_metrics`` — list all catalogued metrics with computability
- ``check_metric`` — check if a single metric is computable
- ``resolve_metric`` — dual-path resolution for a conceptual metric

``check_metric`` uses ``CheckMetricCapabilityUseCase`` so derivatives
metrics report ``computable=False`` when data hasn't been fetched.
"""

import json

from fastmcp import FastMCP

from finbar.core.application.use_cases.check_metric_capability import (
    CheckMetricCapabilityUseCase,
)
from finbar.presentation.dto.metric_serializers import metric_to_dict, result_to_dict
from finbar_strategy_runtime.domain.entities.metric_family import MetricFamily
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog


def register_metric_catalog_tools(mcp: FastMCP) -> None:
    """Register metric catalog discovery tools on the MCP server.

    Args:
        mcp: The FastMCP server instance.
    """
    catalog = UnifiedMetricCatalog()

    @mcp.tool(
        name="list_market_metrics",
        description=(
            "List all catalogued market metrics with honest computability. "
            "Each entry includes name, family, description, computable "
            "(bool), and confidence (actual/proxy/approximation/unavailable). "
            "Use this to discover what metrics exist and which can be "
            "computed for the given interval."
        ),
    )
    async def list_market_metrics(
        symbol: str = "",
        source: str = "",
        interval: str = "1d",
        family: str = "",
    ) -> str:
        """List all metrics with their computability status.

        Args:
            symbol: Asset symbol (e.g. 'BTC'). Reserved for future
                derivatives data checks.
            source: Data source (e.g. 'hyperliquid'). Reserved.
            interval: Bar interval — determines data class
                ('1d'/'1w' → daily_ohlcv, else intraday_ohlcv).
            family: Optional MetricFamily filter (e.g. 'spread', 'volatility').

        Returns:
            JSON string of a list of metric dicts.
        """
        data_class = "intraday_ohlcv" if interval not in ("1d", "1w") else "daily_ohlcv"

        family_enum = None
        if family:
            try:
                family_enum = MetricFamily(family)
            except ValueError:
                pass

        items = catalog.list(family_enum)
        payload = [metric_to_dict(catalog, m, data_class) for m in items]
        return json.dumps(payload, indent=2)

    @mcp.tool(
        name="check_metric",
        description=(
            "Check whether a single named metric is computable. "
            "Returns supported, computable, confidence, and warnings "
            "explaining why a metric may not be available. "
            "For derivatives metrics, also checks if data was fetched."
        ),
    )
    async def check_metric(
        name: str,
        available_data_class: str = "daily_ohlcv",
        symbol: str = "",
    ) -> str:
        """Check capability for a single metric.

        Args:
            name: The metric name (e.g. 'corwin_schultz_spread').
            available_data_class: Data class available
                ('daily_ohlcv', 'intraday_ohlcv', 'external_provider').
            symbol: Asset symbol. Used for derivatives data checks.

        Returns:
            JSON string of a capability result dict.
        """
        use_case = _make_check_metric_capability_use_case()
        result = use_case.execute(
            name=name, symbol=symbol, data_class=available_data_class
        )
        return json.dumps(result_to_dict(result), indent=2)

    @mcp.tool(
        name="resolve_metric",
        description=(
            "Dual-path resolution for a conceptual metric. "
            "Given a concept like 'volatility', selects the best "
            "computation path based on available data class and interval. "
            "Returns the selected metric name and its confidence level."
        ),
    )
    async def resolve_metric(
        concept: str,
        available_data_class: str,
        interval: str = "1d",
        force_proxy: bool = False,
    ) -> str:
        """Resolve the best computation path for a conceptual metric.

        Args:
            concept: Conceptual metric name (e.g. 'volatility', 'spread').
            available_data_class: Data class available.
            interval: Bar interval (e.g. '5min', '1h', '1d').
            force_proxy: If True, skip actual/approximation paths.

        Returns:
            JSON string of a resolution result dict.
        """
        result = catalog.resolve_best(
            concept, available_data_class, interval, force_proxy
        )
        return json.dumps(result_to_dict(result), indent=2)


def _make_check_metric_capability_use_case() -> CheckMetricCapabilityUseCase:
    """Create a CheckMetricCapabilityUseCase with derivatives repo wired.

    Uses deferred import to avoid importing infrastructure at module level
    (the MCP tools module is in the presentation layer and should not
    hard-depend on infrastructure factories at import time).
    """
    try:
        from finbar.presentation.mcp.tools._shared import _get_db

        from finbar.infrastructure.repositories.sql_coinglass_repository import (
            SqlCoinGlassRepository,
        )

        db = _get_db()
        repository = SqlCoinGlassRepository(db)
    except Exception:
        repository = None
    return CheckMetricCapabilityUseCase(repository=repository)
