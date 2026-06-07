"""BacktestPosition — mutable open-position state for backtests."""


class BacktestPosition:
    """Tracks an open position during the backtest bar loop."""

    __slots__ = (
        "size",
        "direction",
        "entry_price",
        "entry_date",
        "stop_price",
        "target_price",
        "liquidation_price",
        "bars_held",
        "entry_commission",
        "entry_slippage",
    )

    def __init__(self) -> None:
        """Initialize an empty position."""
        self.size: float = 0.0
        self.direction: str = ""
        self.entry_price: float = 0.0
        self.entry_date: str = ""
        self.stop_price: float = 0.0
        self.target_price: float = 0.0
        self.liquidation_price: float = 0.0
        self.bars_held: int = 0
        self.entry_commission: float = 0.0
        self.entry_slippage: float = 0.0

    def to_dict(self) -> dict:
        """Return a plain dict snapshot for strategy evaluation."""
        return {
            "size": self.size,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "entry_date": self.entry_date,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "liquidation_price": self.liquidation_price,
            "bars_held": self.bars_held,
            "entry_commission": self.entry_commission,
            "entry_slippage": self.entry_slippage,
        }

    def reset(self) -> None:
        """Reset this position to the flat state."""
        self.size = 0.0
        self.direction = ""
        self.entry_price = 0.0
        self.entry_date = ""
        self.stop_price = 0.0
        self.target_price = 0.0
        self.liquidation_price = 0.0
        self.bars_held = 0
        self.entry_commission = 0.0
        self.entry_slippage = 0.0
