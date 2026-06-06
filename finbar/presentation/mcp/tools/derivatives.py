"""MCP derivatives tools — CoinGlass derivatives market data."""

import json

from fastmcp import FastMCP

from finbar.core.application.dto.fetch_derivatives_request import (
    FetchDerivativesRequest,
)
from finbar.presentation.mcp.presenters.derivatives_presenter import (
    DerivativesPresenter,
)
from finbar.presentation.mcp.tools._shared import (
    _make_fetch_derivatives_use_case,
)


def register_derivatives_tools(mcp: FastMCP) -> None:
    """Register derivatives market data MCP tools."""

    @mcp.tool(
        name="fetch_derivatives",
        description=(
            "Fetch derivatives market metrics from CoinGlass for a crypto "
            "symbol. Returns: funding rate, open interest (with 1h/24h "
            "delta), cumulative volume delta (CVD), long/short ratio, and "
            "liquidations. Crypto only — stocks do not have derivatives data. "
            "Requires COINGLASS_API_KEY environment variable. Data is "
            "automatically persisted to the local database."
        ),
    )
    def fetch_derivatives(
        symbol: str,
        interval: str = "1h",
        start_time: str = "",
        end_time: str = "",
    ) -> str:
        """Fetch and persist derivatives metrics for a crypto symbol."""
        request = FetchDerivativesRequest(
            symbol=symbol.upper(),
            interval=interval,
            start_time=start_time or None,
            end_time=end_time or None,
        )
        result = _make_fetch_derivatives_use_case().execute(request)
        return json.dumps(
            DerivativesPresenter().fetch_result(result),
            indent=2,
            default=str,
        )
