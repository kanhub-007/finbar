"""Convenience entry point — run with: python run_mcp.py

Starts the MCP server. Defaults to stdio transport.
Set FINBAR_TRANSPORT=http to run on port 8001.

All startup logic lives in finbar/startup/mcp.py (composition root).
"""

from finbar.startup.mcp import run

if __name__ == "__main__":
    run()
