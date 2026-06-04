"""MCP tools — finbar operations exposed to MCP clients.

Each tool group lives in its own module and is registered via
a register_*_tools(mcp) function called by register_tools.

Pattern copied from kapsula/presentation/mcp/tools/__init__.py.
"""

from fastmcp import FastMCP

from .jobs import register_job_tools
from .prices import register_price_tools
from .symbols import register_symbol_tools


def register_tools(mcp: FastMCP) -> None:
    """Register all finbar MCP tools on the given server instance."""
    register_symbol_tools(mcp)
    register_price_tools(mcp)
    register_job_tools(mcp)
