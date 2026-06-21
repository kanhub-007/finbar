"""LeverageConfig — value object for margin/leverage settings."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LeverageConfig:
    """Leverage and margin configuration for a backtest run.

    multiplier=1.0 means spot (no leverage).
    multiplier=3.0 means 3× leverage.
    """

    multiplier: float = 1.0
    maintenance_margin_pct: float = 0.0

    @property
    def is_spot(self) -> bool:
        """True when trading without leverage."""
        return self.multiplier <= 1.0

    def liquidation_price(self, entry_price: float, direction: str) -> float:
        """Price at which the position is force-closed.

        Uses an isolated-margin approximation that accounts for the
        configured maintenance margin percentage. When
        ``maintenance_margin_pct == 0.0`` the formula matches the
        previous zero-maintenance model.

        Returns entry_price when leverage <= 1 (spot / no liquidation).
        """
        if self.multiplier <= 1:
            return entry_price
        initial_margin_fraction = 1.0 / self.multiplier
        if direction == "long":
            return entry_price * (
                1.0 - initial_margin_fraction + self.maintenance_margin_pct
            )
        if direction == "short":
            return entry_price * (
                1.0 + initial_margin_fraction - self.maintenance_margin_pct
            )
        raise ValueError(
            f"Unknown direction {direction!r}; expected 'long' or 'short'"
        )

    def max_affordable(self, cash: float, price: float) -> float:
        """Maximum position size given account equity and leverage."""
        if price <= 0.0:
            return 0.0
        return (cash * self.multiplier) / price

    def margin_required(self, position_value: float) -> float:
        """Initial margin needed for a position of given value."""
        if self.multiplier <= 0:
            raise ValueError(
                f"Leverage multiplier must be positive, got {self.multiplier}"
            )
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
        raise ValueError(
            f"Unknown direction {direction!r}; expected 'long' or 'short'"
        )
