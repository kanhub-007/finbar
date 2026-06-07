"""MarginAccount — tracks separate cash and margin balances.

Used when margin_mode == "full". In simplified mode, cash alone
represents equity and margin_book is not consulted.
"""

from dataclasses import dataclass


@dataclass
class MarginAccount:
    """Separate cash and margin accounting for leveraged positions.

    When margin_mode == "simplified", this is never instantiated.
    When margin_mode == "full", equity = cash + unrealized_pnl and
    margin_book tracks locked collateral.

    Attributes:
        cash: Free (unencumbered) cash available for new positions.
        margin_book: Total margin locked across all open positions.
        unrealized_pnl: Mark-to-market PnL on open positions.
        total_borrow_cost: Cumulative borrow costs paid.
        total_funding_paid: Cumulative funding payments made.
    """

    cash: float = 0.0
    margin_book: float = 0.0
    unrealized_pnl: float = 0.0
    total_borrow_cost: float = 0.0
    total_funding_paid: float = 0.0

    @property
    def equity(self) -> float:
        """Free equity available. Cash already reflects locked margin."""
        return self.cash

    @property
    def available_margin(self) -> float:
        """Free equity available to collateralize new positions."""
        return max(0.0, self.equity - self.margin_book)

    def lock_margin(self, amount: float) -> None:
        """Move cash to margin_book for a new position."""
        actual = min(amount, self.cash)
        self.cash -= actual
        self.margin_book += actual

    def release_margin(self, amount: float) -> None:
        """Return margin back to cash on position close."""
        actual = min(amount, self.margin_book)
        self.margin_book -= actual
        self.cash += actual

    def apply_funding(self, payment: float) -> None:
        """Apply a funding payment to cash."""
        self.cash -= payment
        self.total_funding_paid += abs(payment)

    def apply_borrow(self, cost: float) -> None:
        """Apply borrow cost to cash."""
        self.cash -= cost
        self.total_borrow_cost += cost
