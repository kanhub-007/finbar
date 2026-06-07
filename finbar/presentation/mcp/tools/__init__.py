"""MCP tools — finbar operations exposed to MCP clients.

Each tool group lives in its own module and is registered via
a register_*_tools(mcp) function called by register_tools.

"""

from fastmcp import FastMCP

from .analysis import register_analysis_tools
from .derivatives import register_derivatives_tools
from .indicators import register_indicator_tools
from .jobs import register_job_tools
from .optimization import register_optimization_tools
from .prices import register_price_tools
from .signals import register_signal_tools
from .strategy_definition import register_strategy_definition_tools
from .symbols import register_symbol_tools


def register_tools(mcp: FastMCP) -> None:
    """Register all finbar MCP tools on the given server instance."""
    register_symbol_tools(mcp)
    register_price_tools(mcp)
    register_job_tools(mcp)
    register_analysis_tools(mcp)
    register_derivatives_tools(mcp)
    register_indicator_tools(mcp)
    register_optimization_tools(mcp)
    register_signal_tools(mcp)
    register_strategy_definition_tools(mcp)
