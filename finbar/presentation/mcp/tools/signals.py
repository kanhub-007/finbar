"""MCP signal interpretation tools — confidence scoring, risk flags."""

import json

from fastmcp import FastMCP

from finbar.core.application.dto.compute_signals_request import ComputeSignalsRequest
from finbar.presentation.mcp.presenters.signal_presenter import SignalPresenter
from finbar.presentation.mcp.tools._shared import _make_compute_signals_use_case


def register_signal_tools(mcp: FastMCP) -> None:
    """Register signal interpretation MCP tools."""

    @mcp.tool(
        name="compute_signals",
        description=(
            "Compute signal interpretation columns from already-enriched "
            "OHLCV bars. Adds: rsi_zone (5-tier), adx_conviction (20-95), "
            "is_squeeze, is_overextended, is_weak_trend, is_low_volume, "
            "near_resistance, near_support, confidence_score (0-100). "
            "Requires bars with indicators: rsi_14, adx, atr, rvol, "
            "swing_high_20, swing_low_20, bb_upper_20, bb_lower_20. "
            "Returns enriched bars with signal columns added."
        ),
    )
    def compute_signals(
        bars_json: str,
        symbol: str = "",
        interval: str = "",
    ) -> str:
        """Compute signal interpretation columns from enriched bars."""
        try:
            bars = json.loads(bars_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid bars_json: {exc}"})
        if not isinstance(bars, list):
            return json.dumps({"error": "bars_json must be a JSON array"})

        result = _make_compute_signals_use_case().execute(
            ComputeSignalsRequest(bars=bars, symbol=symbol, interval=interval)
        )
        return json.dumps(
            SignalPresenter.compute_result(result), indent=2, default=str
        )
