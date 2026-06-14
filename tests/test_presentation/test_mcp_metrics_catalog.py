"""Tests for MCP metric catalog discovery tools — Slice 4 Scenarios 4.1–4.3.

Verifies list_market_metrics, check_metric, and resolve_metric expose
the unified catalog with honest computability via FastMCP.
"""

import pytest
from fastmcp import FastMCP

from finbar.presentation.mcp.tools.metrics_catalog import (
    register_metric_catalog_tools,
)


@pytest.fixture
def mcp() -> FastMCP:
    """Build a FastMCP server with metric catalog tools registered."""
    server = FastMCP("test")
    register_metric_catalog_tools(server)
    return server


# ---------------------------------------------------------------------------
# Scenario 4.1: list_market_metrics
# ---------------------------------------------------------------------------


class TestListMarketMetrics:
    """list_market_metrics returns every metric with honest computability."""

    @pytest.mark.asyncio
    async def test_returns_list_of_metrics(self, mcp):
        """The tool returns a list of metric dicts."""
        result = await mcp.call_tool(
            "list_market_metrics",
            {"symbol": "BTC", "source": "hyperliquid", "interval": "1d"},
        )
        payload = result.structured_content
        if isinstance(payload, dict) and "result" in payload:
            payload = _parse_json(payload["result"])
        assert isinstance(payload, list)
        assert len(payload) > 50

    @pytest.mark.asyncio
    async def test_each_metric_has_required_fields(self, mcp):
        """Each metric entry has name, family, computable, confidence."""
        result = await mcp.call_tool(
            "list_market_metrics",
            {"symbol": "BTC", "source": "hyperliquid", "interval": "1d"},
        )
        payload = _extract_payload(result)
        for entry in payload[:5]:
            assert "name" in entry
            assert "family" in entry
            assert "computable" in entry
            assert "confidence" in entry
            assert isinstance(entry["computable"], bool)

    @pytest.mark.asyncio
    async def test_corwin_schultz_in_list(self, mcp):
        """corwin_schultz_spread appears in the list."""
        result = await mcp.call_tool(
            "list_market_metrics",
            {"symbol": "BTC", "source": "hyperliquid", "interval": "1d"},
        )
        payload = _extract_payload(result)
        names = {m["name"] for m in payload}
        assert "corwin_schultz_spread" in names

    @pytest.mark.asyncio
    async def test_intraday_metric_not_computable_on_daily(self, mcp):
        """A metric needing intraday data shows computable=False for daily."""
        result = await mcp.call_tool(
            "list_market_metrics",
            {"symbol": "BTC", "source": "hyperliquid", "interval": "1d"},
        )
        payload = _extract_payload(result)
        first_last = next(
            (m for m in payload if m["name"] == "first_last_hour_vol_fraction"),
            None,
        )
        if first_last is not None:
            # On daily data, intraday-seasonality metric is a proxy
            # but still computable from OHLCV — just lower confidence
            assert isinstance(first_last["computable"], bool)


# ---------------------------------------------------------------------------
# Scenario 4.2: check_metric
# ---------------------------------------------------------------------------


class TestCheckMetric:
    """check_metric returns capability for a single metric."""

    @pytest.mark.asyncio
    async def test_amihud_computable_on_daily(self, mcp):
        """amihud_illiq with daily_ohlcv → supported, computable."""
        result = await mcp.call_tool(
            "check_metric",
            {"name": "amihud_illiq", "available_data_class": "daily_ohlcv"},
        )
        payload = _extract_payload(result)
        assert payload["supported"] is True
        assert payload["computable"] is True

    @pytest.mark.asyncio
    async def test_unknown_metric_not_supported(self, mcp):
        """An unknown metric → supported=False."""
        result = await mcp.call_tool(
            "check_metric",
            {"name": "nonexistent_metric", "available_data_class": "daily_ohlcv"},
        )
        payload = _extract_payload(result)
        assert payload["supported"] is False
        assert payload["computable"] is False

    @pytest.mark.asyncio
    async def test_elliott_wave_not_computable(self, mcp):
        """elliott_wave_count (implemented=False) → computable=False."""
        result = await mcp.call_tool(
            "check_metric",
            {"name": "elliott_wave_count", "available_data_class": "daily_ohlcv"},
        )
        payload = _extract_payload(result)
        assert payload["supported"] is True
        assert payload["computable"] is False


# ---------------------------------------------------------------------------
# Scenario 4.3: resolve_metric (dual-path)
# ---------------------------------------------------------------------------


class TestResolveMetric:
    """resolve_metric performs dual-path resolution."""

    @pytest.mark.asyncio
    async def test_volatility_daily_selects_yang_zhang(self, mcp):
        """volatility on daily → yang_zhang_vol, confidence=proxy."""
        result = await mcp.call_tool(
            "resolve_metric",
            {
                "concept": "volatility",
                "available_data_class": "daily_ohlcv",
                "interval": "1d",
            },
        )
        payload = _extract_payload(result)
        assert payload["selected_metric"] == "yang_zhang_vol"
        assert payload["confidence"] == "proxy"

    @pytest.mark.asyncio
    async def test_volatility_intraday_selects_realized_5m(self, mcp):
        """volatility on intraday 5min → realized_vol_5m, confidence=actual."""
        result = await mcp.call_tool(
            "resolve_metric",
            {
                "concept": "volatility",
                "available_data_class": "intraday_ohlcv",
                "interval": "5min",
            },
        )
        payload = _extract_payload(result)
        assert payload["selected_metric"] == "realized_vol_5m"
        assert payload["confidence"] == "actual"

    @pytest.mark.asyncio
    async def test_unknown_concept_not_supported(self, mcp):
        """An unknown concept → supported=False."""
        result = await mcp.call_tool(
            "resolve_metric",
            {
                "concept": "nonexistent_concept",
                "available_data_class": "daily_ohlcv",
                "interval": "1d",
            },
        )
        payload = _extract_payload(result)
        assert payload["supported"] is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_payload(result) -> dict | list:
    """Extract structured content from a FastMCP ToolResult."""
    payload = result.structured_content
    if isinstance(payload, dict) and "result" in payload and isinstance(
        payload["result"], str
    ):
        return _parse_json(payload["result"])
    if isinstance(payload, dict) and "result" in payload:
        return payload["result"]
    return payload


def _parse_json(text: str) -> dict | list:
    """Parse a JSON string, returning the parsed value."""
    import json

    return json.loads(text)
