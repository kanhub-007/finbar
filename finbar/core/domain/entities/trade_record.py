"""TradeRecord — immutable DTO for a completed backtest trade."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TradeRecord:
    """A completed round-trip trade with full cost breakdown."""

    entry_date: str
    """ISO-format timestamp of the entry fill."""

    exit_date: str
    """ISO-format timestamp of the exit fill."""

    entry_price: float
    """Price at which the position was entered."""

    exit_price: float
    """Price at which the position was exited."""

    size: float
    """Absolute position size (number of shares/contracts)."""

    gross_pnl: float
    """Gross PnL before costs."""

    net_pnl: float
    """Net PnL after all costs: commissions, borrow, slippage via price."""

    entry_commission: float
    """Commission paid on entry."""

    exit_commission: float
    """Commission paid on exit."""

    borrow_cost: float
    """Total borrow cost accrued over the holding period."""

    total_commission: float
    """Sum of entry and exit commissions."""

    pnl_pct: float
    """Net PnL as a fraction of entry notional."""

    duration_bars: int
    """Number of bars the position was held."""

    direction: str
    """Trade direction: long or short."""

    exit_reason: str
    """Reason the position was closed."""

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict matching the existing trade schema."""
        return {
            "entry_date": self.entry_date,
            "exit_date": self.exit_date,
            "entry_price": round(self.entry_price, 8),
            "exit_price": round(self.exit_price, 8),
            "size": self.size,
            "pnl": round(self.net_pnl, 2),
            "net_pnl": round(self.net_pnl, 2),
            "gross_pnl": round(self.gross_pnl, 2),
            "entry_commission": round(self.entry_commission, 2),
            "exit_commission": round(self.exit_commission, 2),
            "borrow_cost": round(self.borrow_cost, 2),
            "total_commission": round(self.total_commission, 2),
            "pnl_pct": round(self.pnl_pct, 4),
            "duration_bars": self.duration_bars,
            "metadata": {
                "direction": self.direction,
                "exit_reason": self.exit_reason,
            },
        }
