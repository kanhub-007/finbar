"""Tests for execution control parameter descriptions on MCP tools.

Locks in the agent-facing documentation for the parameters that are easiest
to misuse: ``risk_per_trade`` (decimal fraction, not percent) and ``leverage``
(capped by stop/liquidation distance). Without these descriptions, callers
see only the bare name and default value, which has caused real bugs (e.g.
passing risk_per_trade=5 thinking it means 5%).
"""

import pytest
from fastmcp import FastMCP

from finbar.presentation.mcp.tools import register_tools

# Every tool that exposes execution controls should describe them clearly.
EXPECTED_TOOLS = [
    "run_backtest",
    "run_portfolio_backtest",
    "run_strategy_pipeline",
    "backtest_strategy_definition",
    "start_optimization_job",
    "start_walk_forward_job",
]


@pytest.fixture
def mcp() -> FastMCP:
    """Build a FastMCP server with all tools registered."""
    server = FastMCP("test")
    register_tools(server)
    return server


@pytest.mark.asyncio
async def test_risk_per_trade_is_described_as_decimal(mcp: FastMCP) -> None:
    """Every risk_per_trade param must warn that it is a decimal fraction.

    Regression: previously the param had no description, so callers passed
    ``5`` meaning 5% and silently got a 500% risk budget.
    """
    tools = {t.name: t for t in await mcp.list_tools()}
    for name in EXPECTED_TOOLS:
        tool = tools.get(name)
        assert tool is not None, f"missing tool {name}"
        props = tool.parameters.get("properties", {})
        if "risk_per_trade" not in props:
            continue  # run_backtest doesn't expose this one
        desc = props["risk_per_trade"].get("description", "")
        assert "DECIMAL" in desc.upper(), (
            f"{name}.risk_per_trade description must say DECIMAL: {desc!r}"
        )
        # Warn against the literal '5 = 500%' footgun
        assert "500%" in desc, (
            f"{name}.risk_per_trade description must warn about the 5=>500% bug: {desc!r}"
        )
        # Default unchanged
        assert props["risk_per_trade"].get("default") == 0.02


@pytest.mark.asyncio
async def test_leverage_documents_liquidation_constraint(mcp: FastMCP) -> None:
    """Every leverage param must mention the stop/liquidation relationship."""
    tools = {t.name: t for t in await mcp.list_tools()}
    for name in EXPECTED_TOOLS:
        tool = tools.get(name)
        assert tool is not None, f"missing tool {name}"
        props = tool.parameters.get("properties", {})
        if "leverage" not in props:
            continue
        desc = props["leverage"].get("description", "").lower()
        # Must explain that leverage caps position size
        assert "buying-power" in desc or "buying power" in desc, (
            f"{name}.leverage description must mention buying power: {desc!r}"
        )
        # Must warn that stops interact with liquidation
        assert "liquidation" in desc, (
            f"{name}.leverage description must mention liquidation: {desc!r}"
        )
        assert props["leverage"].get("default") == 1.0


@pytest.mark.asyncio
async def test_all_execution_fields_have_descriptions(mcp: FastMCP) -> None:
    """No execution control should have an empty description."""
    execution_params = {
        "risk_per_trade",
        "leverage",
        "risk_mode",
        "commission_pct",
        "slippage_pct",
        "cap_explicit_size",
        "reject_oversized_explicit_orders",
        "allow_negative_cash",
        "market_calendar",
        "borrow_fee_annual_pct",
        "margin_mode",
        "maintenance_margin_pct",
        "enable_funding",
        "funding_rate",
    }
    tools = {t.name: t for t in await mcp.list_tools()}
    for name in EXPECTED_TOOLS:
        tool = tools.get(name)
        assert tool is not None, f"missing tool {name}"
        props = tool.parameters.get("properties", {})
        for param in execution_params & props.keys():
            desc = props[param].get("description", "")
            assert desc, f"{name}.{param} has empty description"
