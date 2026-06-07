"""Tests for machine-readable strategy capability metadata."""

from finbar.core.application.services.strategy_capability_service import (
    StrategyCapabilityService,
)


def test_capabilities_include_execution_controls_and_diagnostics():
    """Capabilities advertise execution controls and result diagnostics."""
    capabilities = StrategyCapabilityService().get_capabilities()

    controls = capabilities["execution_controls"]
    diagnostics = capabilities["result_diagnostics"]

    assert controls["risk_mode"] == ["fixed_equity_risk", "leverage_scaled_risk"]
    assert controls["market_calendar"] == ["equity_regular_hours", "crypto_24_7"]
    assert "commission_pct" in controls
    assert "slippage_pct" in controls
    assert "trust_diagnostics" in diagnostics
    assert "annualization_warning" in diagnostics
