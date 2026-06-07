"""LeverageConfig — value object for margin/leverage settings."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LeverageConfig:
    """Leverage and margin configuration for a backtest run.

    multiplier=1.0 means spot (no leverage).
    multiplier=3.0 means 3× leverage.
    """

    multiplier: float = 1.0

    @property
    def is_spot(self) -> bool:
        """True when trading without leverage."""
        return self.multiplier <= 1.0

    def liquidation_price(self, entry_price: float, direction: str) -> float:
        """Price at which the position is force-closed.

        Assumes isolated margin with zero maintenance margin buffer.
        In practice exchanges use ~0.5-1% maintenance margin, but
        we use the exact price for a conservative backtest.
        """
        if direction == "long":
            return entry_price * (1.0 - 1.0 / self.multiplier)
        if direction == "short":
            return entry_price * (1.0 + 1.0 / self.multiplier)
        return entry_price

    def max_affordable(self, cash: float, price: float) -> float:
        """Maximum position size given account equity and leverage."""
        if price <= 0.0:
            return 0.0
        return (cash * self.multiplier) / price

    def margin_required(self, position_value: float) -> float:
        """Initial margin needed for a position of given value."""
        if self.multiplier <= 0:
            return position_value
        return position_value / self.multiplier

    def validate_stop(
        self,
        stop_price: float,
        entry_price: float,
        direction: str,
    ) -> bool:
        """Return True when the stop is inside the liquidation boundary."""
        if self.is_spot:
            return True
        liq = self.liquidation_price(entry_price, direction)
        if direction == "long":
            return stop_price > liq
        if direction == "short":
            return stop_price < liq
        return False
