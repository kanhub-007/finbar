"""MCP server startup — composition root for the MCP transport.

Pattern copied from kapsula/startup/mcp.py.
Creates the FastMCP server, wires dependencies, and provides the CLI runner.
"""

import logging
import os

from dotenv import load_dotenv
from fastmcp import FastMCP

from finbar.startup.bootstrap import bootstrap

load_dotenv()
logger = logging.getLogger(__name__)


def create_server() -> FastMCP:
    """Build the FastMCP server with database bootstrapped and tools registered.

    Returns:
        Configured FastMCP server instance ready to run.
    """
    bootstrap()

    server = FastMCP(
        name="finbar",
        instructions=(
            "Finbar is a financial OHLCV bars microservice. "
            "Call get_usage_guide() first for a complete usage guide. "
            "\n\n"
            "QUICK REFERENCE:\n"
            "• FRESH DATA: fetch_price_history() — background job, returns job_id. "
            "Poll with get_job_progress(), retrieve with get_job_results().\n"
            "• CACHED DATA: get_cached_prices() — instant from local SQLite.\n"
            "• get_symbol_info() for company metadata.\n"
            "• get_latest_quote() for the most recent bar.\n"
            "• delete_cached_prices() to manage cache.\n"
            "• list_cached_symbols() to see what's stored.\n"
            "• Full details: call get_usage_guide()"
        ),
    )

    from finbar.presentation.mcp.tools import register_tools

    register_tools(server)

    config = get_transport_config()
    logger.info("MCP server configured: transport=%s", config["transport"])
    if config["transport"] == "http":
        logger.info("HTTP transport: %s:%s", config["host"], config["port"])

    return server


def get_transport_config() -> dict:
    """Read transport configuration from environment variables."""
    return {
        "transport": os.getenv("FINBAR_TRANSPORT", "stdio").lower(),
        "host": os.getenv("FINBAR_HOST", "127.0.0.1"),
        "port": int(os.getenv("FINBAR_PORT", "8001")),
    }


def run() -> None:
    """Start the MCP server. Called by CLI entry points."""
    server = create_server()
    config = get_transport_config()

    if config["transport"] == "http":
        logger.info(
            "Starting MCP server on http://%s:%s",
            config["host"],
            config["port"],
        )
        server.run(
            transport="streamable-http",
            host=config["host"],
            port=config["port"],
        )
    else:
        logger.info("Starting MCP server on stdio")
        server.run(transport="stdio")
