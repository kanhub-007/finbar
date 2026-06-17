"""Reusable pydantic Field descriptors for backtest execution controls.

These provide consistent, agent-facing descriptions across every MCP and REST
tool that exposes execution controls. Without them, callers see only the bare
parameter name and default value, which has caused real bugs — e.g. passing
``risk_per_trade=5`` to mean "5%" when it actually means "500% of equity".

Each descriptor documents the unit, the default, the formula it participates
in, and any cross-parameter constraints (such as leverage vs. liquidation).
Import and use as the default value of the matching function parameter:

    from finbar.presentation.mcp.tools._execution_fields import (
        RISK_PER_TRADE, LEVERAGE,
    )

    def backtest(..., risk_per_trade: float = RISK_PER_TRADE,
                  leverage: float = LEVERAGE): ...
"""

from __future__ import annotations

from pydantic import Field

# -- Sizing / risk ----------------------------------------------------------

RISK_PER_TRADE: float = Field(
    default=0.02,
    description=(
        "Fraction of portfolio equity risked at the protective stop. "
        "DECIMAL FRACTION, not percent: pass 0.05 for 5%, 0.02 for 2%. "
        "DO NOT pass 5 (that means 500% of equity). Used only when the "
        "strategy has a stop and the risk-based size fits within buying "
        "power; otherwise the affordability cap (leverage * cash / price) "
        "governs position size."
    ),
)

LEVERAGE: float = Field(
    default=1.0,
    description=(
        "Buying-power multiplier. 1.0 = spot (no leverage), 3.0 = 3x, "
        "10.0 = 10x. Sets the affordability cap: "
        "max_size = (cash * leverage) / entry_price. The strategy's stop "
        "must stay ABOVE the liquidation price "
        "(long: entry * (1 - 1/leverage + maintenance_margin_pct)) or the "
        "entry is REJECTED. Wider stops (e.g. larger atr_stop_mult) allow "
        "higher leverage; tight stops cap the usable leverage."
    ),
)

RISK_MODE: str = Field(
    default="fixed_equity_risk",
    description=(
        "How the risk budget scales with leverage. 'fixed_equity_risk' "
        "(default): risk_per_trade is a flat fraction of equity regardless "
        "of leverage. 'leverage_scaled_risk': multiplies the risk budget by "
        "leverage (aggressive; can over-leverage the stop-loss impact)."
    ),
)

CAP_EXPLICIT_SIZE: bool = Field(
    default=True,
    description=(
        "When the strategy sets an explicit position_size, cap it to "
        "available buying power. Set False with care — uncapped sizes can "
        "produce unrealistic fills."
    ),
)

REJECT_OVERSIZED_EXPLICIT_ORDERS: bool = Field(
    default=False,
    description=(
        "When True and an explicit strategy size exceeds buying power, the "
        "order is rejected instead of silently capped. Use for stricter "
        "realism."
    ),
)

ALLOW_NEGATIVE_CASH: bool = Field(
    default=False,
    description=(
        "Allow fills that overdraw cash / buying power. Intended only for "
        "advanced 'what-if' simulations. Default False enforces realistic "
        "account constraints."
    ),
)

# -- Costs ------------------------------------------------------------------

COMMISSION_PCT: float = Field(
    default=0.0,
    description=(
        "Commission per side as a DECIMAL fraction of trade value. "
        "0.001 = 0.1% = 10 bps. Applied to both entry and exit."
    ),
)

SLIPPAGE_PCT: float = Field(
    default=0.0,
    description=(
        "Directional slippage per fill as a DECIMAL fraction. "
        "0.001 = 0.1%. Applied to entry and exit prices (worsens the fill)."
    ),
)

BORROW_FEE_ANNUAL_PCT: float = Field(
    default=0.0,
    description=(
        "Annual borrow fee for SHORT positions as a DECIMAL. 0.03 = 3%/yr. "
        "Accrues from entry to exit on the entry notional. Longs are never "
        "charged borrow."
    ),
)

# -- Margin / funding -------------------------------------------------------

MARGIN_MODE: str = Field(
    default="simplified",
    description=(
        "Margin accounting mode. 'simplified' (default): isolated-margin "
        "approximation with a liquidation-price model. 'full': tracks "
        "initial and maintenance margin explicitly (more realistic for "
        "extended holds)."
    ),
)

MAINTENANCE_MARGIN_PCT: float = Field(
    default=0.005,
    description=(
        "Maintenance margin fraction of position notional (isolated margin). "
        "Default 0.005 = 0.5%. Raises the liquidation price slightly: "
        "liq_long = entry * (1 - 1/leverage + maintenance_margin_pct)."
    ),
)

ENABLE_FUNDING: bool = Field(
    default=False,
    description=(
        "Apply per-bar funding payments to open positions (perpetual "
        "swaps). Combined with funding_rate. Longs pay when funding is "
        "positive, shorts receive."
    ),
)

FUNDING_RATE: float = Field(
    default=0.0001,
    description=(
        "Funding rate per bar as a DECIMAL. 0.0001 = 1 bp per interval. "
        "Only applies when enable_funding=True."
    ),
)

MARKET_CALENDAR: str = Field(
    default="equity_regular_hours",
    description=(
        "Calendar for annualization and session logic. "
        "'equity_regular_hours' (default): 252 days/yr, 6.5h/day. "
        "'crypto_24_7': 365 days/yr, 24h/day."
    ),
)

__all__ = [
    "ALLOW_NEGATIVE_CASH",
    "BORROW_FEE_ANNUAL_PCT",
    "CAP_EXPLICIT_SIZE",
    "COMMISSION_PCT",
    "ENABLE_FUNDING",
    "FUNDING_RATE",
    "LEVERAGE",
    "MAINTENANCE_MARGIN_PCT",
    "MARGIN_MODE",
    "MARKET_CALENDAR",
    "REJECT_OVERSIZED_EXPLICIT_ORDERS",
    "RISK_MODE",
    "RISK_PER_TRADE",
    "SLIPPAGE_PCT",
]
