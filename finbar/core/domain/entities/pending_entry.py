"""PendingEntry — typed state for a deferred entry signal in the backtest loop.

Pure dataclass — no behavior, no ORM, no framework dependencies.
"""

from dataclasses import dataclass


@dataclass
class PendingEntry:
    """Signal awaiting execution at the next bar's open (conservative mode)."""

    direction: str = ""
    """Trade direction: "long" or "short"."""

    stop_price: float = 0.0
    """Stop-loss price level from the signal."""

    target_price: float = 0.0
    """Take-profit price level from the signal."""

    position_size: int = 0
    """Explicit position size requested by the strategy. 0 means risk-size."""

    explicit_size: bool = False
    """True if the strategy explicitly set position_size (skip cash constraint)."""

    risk_per_trade: float = 0.02
    """Fraction of portfolio value to risk when engine computes position size."""
