"""Tests for compact backtest result projections used by MCP tools."""

from finbar.core.application.backtest_result_projection import compact_backtest_response


class TestBacktestResultProjection:
    """Black-box tests for compact result serialization."""

    def test_summary_includes_causal_safety_metadata(self):
        """MCP summary projections expose enrichment safety fields."""
        response = compact_backtest_response(
            "result-1",
            {
                "strategy_name": "causal_strategy",
                "symbol": "TEST",
                "interval": "1h",
                "bar_count": 10,
                "enrichment_mode": "live_parity_streaming",
                "live_parity_safe": True,
                "parity_warnings": [],
                "trades": [],
                "equity_curve": [],
            },
        )

        summary = response["summary"]
        assert summary["enrichment_mode"] == "live_parity_streaming"
        assert summary["live_parity_safe"] is True
        assert summary["parity_warnings"] == []
