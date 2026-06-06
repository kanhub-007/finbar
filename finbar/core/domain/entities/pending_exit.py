"""PendingExit — typed state for a deferred exit signal in the backtest loop.

Pure dataclass — no behavior, no ORM, no framework dependencies.
"""

from dataclasses import dataclass


@dataclass
class PendingExit:
    """Exit signal awaiting execution at the next bar's open."""

    direction: str = ""
    """Direction being exited: "long" or "short"."""

    confidence: float = 0.0
    """Signal confidence from the original exit signal."""
