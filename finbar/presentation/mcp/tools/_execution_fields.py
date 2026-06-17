"""Reusable Pydantic Field descriptors for backtest execution controls.

These provide consistent, agent-facing descriptions across every MCP and REST
tool that exposes execution controls. Each descriptor is a ``pydantic.FieldInfo``
object; FastMCP introspects the function signature at registration time and
extracts ``.default`` and ``.description`` automatically.

The type annotation on each constant is deliberately omitted — the objects are
``FieldInfo`` instances, not plain floats/strings. Use them as default values
in MCP tool function signatures.

Also provides ``build_execution_config()`` — a shared builder that eliminates
copy-paste ExecutionConfig construction across tools.
"""

from __future__ import annotations

from pydantic import Field as PydanticField

from finbar.core.domain.entities.execution_config import ExecutionConfig

# -- Sizing / risk ----------------------------------------------------------

RISK_PER_TRADE = PydanticField(
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

LEVERAGE = PydanticField(
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

RISK_MODE = PydanticField(
    default="fixed_equity_risk",
    description=(
        "How the risk budget scales with leverage. 'fixed_equity_risk' "
        "(default): risk_per_trade is a flat fraction of equity regardless "
        "of leverage. 'leverage_scaled_risk': multiplies the risk budget by "
        "leverage (aggressive; can over-leverage the stop-loss impact)."
    ),
)

CAP_EXPLICIT_SIZE = PydanticField(
    default=True,
    description=(
        "When the strategy sets an explicit position_size, cap it to "
        "available buying power. Set False with care — uncapped sizes can "
        "produce unrealistic fills."
    ),
)

REJECT_OVERSIZED_EXPLICIT_ORDERS = PydanticField(
    default=False,
    description=(
        "When True and an explicit strategy size exceeds buying power, the "
        "order is rejected instead of silently capped. Use for stricter "
        "realism."
    ),
)

ALLOW_NEGATIVE_CASH = PydanticField(
    default=False,
    description=(
        "Allow fills that overdraw cash / buying power. Intended only for "
        "advanced 'what-if' simulations. Default False enforces realistic "
        "account constraints."
    ),
)

# -- Costs ------------------------------------------------------------------

COMMISSION_PCT = PydanticField(
    default=0.0,
    description=(
        "Commission per side as a DECIMAL fraction of trade value. "
        "0.001 = 0.1% = 10 bps. Applied to both entry and exit."
    ),
)

SLIPPAGE_PCT = PydanticField(
    default=0.0,
    description=(
        "Directional slippage per fill as a DECIMAL fraction. "
        "0.001 = 0.1%. Applied to entry and exit prices (worsens the fill)."
    ),
)

BORROW_FEE_ANNUAL_PCT = PydanticField(
    default=0.0,
    description=(
        "Annual borrow fee for SHORT positions as a DECIMAL. 0.03 = 3%/yr. "
        "Accrues from entry to exit on the entry notional. Longs are never "
        "charged borrow."
    ),
)

# -- Margin / funding -------------------------------------------------------

MARGIN_MODE = PydanticField(
    default="simplified",
    description=(
        "Margin accounting mode. 'simplified' (default): isolated-margin "
        "approximation with a liquidation-price model. 'full': tracks "
        "initial and maintenance margin explicitly (more realistic for "
        "extended holds)."
    ),
)

MAINTENANCE_MARGIN_PCT = PydanticField(
    default=0.005,
    description=(
        "Maintenance margin fraction of position notional (isolated margin). "
        "Default 0.005 = 0.5%. Raises the liquidation price slightly: "
        "liq_long = entry * (1 - 1/leverage + maintenance_margin_pct)."
    ),
)

ENABLE_FUNDING = PydanticField(
    default=False,
    description=(
        "Apply per-bar funding payments to open positions (perpetual "
        "swaps). Combined with funding_rate. Longs pay when funding is "
        "positive, shorts receive."
    ),
)

FUNDING_RATE = PydanticField(
    default=0.0001,
    description=(
        "Funding rate per bar as a DECIMAL. 0.0001 = 1 bp per interval. "
        "Only applies when enable_funding=True."
    ),
)

MARKET_CALENDAR = PydanticField(
    default="equity_regular_hours",
    description=(
        "Calendar for annualization and session logic. "
        "'equity_regular_hours' (default): 252 days/yr, 6.5h/day. "
        "'crypto_24_7': 365 days/yr, 24h/day."
    ),
)

RISK_PRICE_BASIS = PydanticField(
    default="signal_close",
    description=(
        "Anchor for stop/target prices: 'signal_close' or 'entry_fill'."
    ),
)

BORROW_TIME_BASIS = PydanticField(
    default="calendar_day",
    description=(
        "Borrow cost time basis: 'calendar_day' or 'timestamp_delta'."
    ),
)

# ── Shared builder (eliminates copy-paste across tools) ───────────────────


def build_execution_config(
    *,
    leverage_multiplier: float = 1.0,
    risk_mode: str = "fixed_equity_risk",
    commission_pct: float = 0.0,
    slippage_pct: float = 0.0,
    cap_explicit_size: bool = True,
    reject_oversized_explicit_orders: bool = False,
    allow_negative_cash: bool = False,
    market_calendar: str = "equity_regular_hours",
    borrow_fee_annual_pct: float = 0.0,
    margin_mode: str = "simplified",
    maintenance_margin_pct: float = 0.005,
    enable_funding: bool = False,
    funding_rate: float = 0.0001,
    risk_price_basis: str = "signal_close",
    borrow_time_basis: str = "calendar_day",
) -> ExecutionConfig:
    """Build an ExecutionConfig from named arguments.

    Use this in every MCP/REST tool that constructs an ExecutionConfig
    instead of writing the same 12+ fields inline.
    """
    return ExecutionConfig(
        leverage_multiplier=leverage_multiplier,
        risk_mode=risk_mode,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
        cap_explicit_size=cap_explicit_size,
        reject_oversized_explicit_orders=reject_oversized_explicit_orders,
        allow_negative_cash=allow_negative_cash,
        market_calendar=market_calendar,
        borrow_fee_annual_pct=borrow_fee_annual_pct,
        margin_mode=margin_mode,
        maintenance_margin_pct=maintenance_margin_pct,
        enable_funding=enable_funding,
        funding_rate=funding_rate,
        risk_price_basis=risk_price_basis,
        borrow_time_basis=borrow_time_basis,
    )


__all__ = [
    "ALLOW_NEGATIVE_CASH",
    "BORROW_FEE_ANNUAL_PCT",
    "BORROW_TIME_BASIS",
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
    "RISK_PRICE_BASIS",
    "RISK_PER_TRADE",
    "SLIPPAGE_PCT",
    "build_execution_config",
]
