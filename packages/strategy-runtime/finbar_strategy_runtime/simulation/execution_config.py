"""ExecutionConfig — value object for backtest execution settings."""

from dataclasses import dataclass

from finbar_strategy_runtime.simulation.enums import (
    BorrowTimeBasis,
    MarginMode,
    MarketCalendar,
    RiskMode,
    RiskPriceBasis,
)


def _validate_enum_field(field_name: str, value: str, enum_cls) -> None:
    """Raise ValueError if *value* is not a member of *enum_cls*."""
    allowed = {member.value for member in enum_cls}
    if value not in allowed:
        raise ValueError(
            f"ExecutionConfig.{field_name}={value!r} is not one of "
            f"{sorted(allowed)} (typo?)"
        )


@dataclass(frozen=True)
class ExecutionConfig:
    """Execution, risk, and accounting settings for one backtest run."""

    commission_pct: float = 0.0
    """Percentage commission per side, expressed as a decimal."""

    slippage_pct: float = 0.0
    """Directional slippage percentage, expressed as a decimal."""

    leverage_multiplier: float = 1.0
    """Leverage multiplier. 1.0 means spot / no leverage."""

    risk_mode: str = "fixed_equity_risk"
    """Risk sizing mode: fixed_equity_risk or leverage_scaled_risk."""

    cap_explicit_size: bool = True
    """Cap explicit strategy sizes to available buying power when true."""

    reject_oversized_explicit_orders: bool = False
    """Reject oversized explicit strategy orders instead of capping them."""

    allow_negative_cash: bool = False
    """Allow fills that overdraw cash / buying power when true."""

    market_calendar: str = "equity_regular_hours"
    """Calendar used for annualization assumptions."""

    borrow_fee_annual_pct: float = 0.0
    """Annual borrow fee for short positions, expressed as a decimal."""

    margin_mode: str = "simplified"
    """Margin accounting mode: simplified or full."""

    maintenance_margin_pct: float = 0.005
    """Maintenance margin fraction of position notional. Default 0.5%."""

    enable_funding: bool = False
    """Apply per-bar funding payments to open positions (perpetual swaps)."""

    funding_rate: float = 0.0001
    """Funding rate per interval. Default 0.01%% per bar."""

    risk_price_basis: str = "signal_close"
    """Anchor for stop/target prices: signal_close or entry_fill."""

    borrow_time_basis: str = "calendar_day"
    """Borrow cost time basis: calendar_day or timestamp_delta."""

    def risk_budget_multiplier(self) -> float:
        """Return the multiplier applied to the equity risk budget."""
        if self.risk_mode == RiskMode.LEVERAGE_SCALED_RISK.value:
            return max(self.leverage_multiplier, 1.0)
        return 1.0

    def __post_init__(self) -> None:
        """Validate enum-backed string fields so typos fail fast."""
        _validate_enum_field("risk_mode", self.risk_mode, RiskMode)
        _validate_enum_field("margin_mode", self.margin_mode, MarginMode)
        _validate_enum_field(
            "risk_price_basis", self.risk_price_basis, RiskPriceBasis
        )
        _validate_enum_field(
            "borrow_time_basis", self.borrow_time_basis, BorrowTimeBasis
        )
        _validate_enum_field(
            "market_calendar", self.market_calendar, MarketCalendar
        )
