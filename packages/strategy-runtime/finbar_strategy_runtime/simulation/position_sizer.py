"""PositionSizer — risk-based and explicit position sizing with affordability caps."""

from __future__ import annotations

from finbar_strategy_runtime.simulation.backtest_diagnostic import (
    BacktestDiagnostic,  # noqa: F401
)
from finbar_strategy_runtime.simulation.execution_config import ExecutionConfig
from finbar_strategy_runtime.simulation.leverage_config import LeverageConfig
from finbar_strategy_runtime.simulation.pending_entry import PendingEntry
from finbar_strategy_runtime.simulation.simulation_state import SimulationState

_DEFAULT_POSITION_SIZE = 100.0


class PositionSizer:
    """Compute position size and enforce buying-power affordability."""

    def __init__(self, config: ExecutionConfig) -> None:
        """Create a sizer bound to one execution configuration."""
        self._config = config
        self._leverage = LeverageConfig(
            multiplier=config.leverage_multiplier,
            maintenance_margin_pct=config.maintenance_margin_pct,
        )

    def resolve(
        self,
        state: SimulationState,
        entry: PendingEntry,
        entry_price: float,
        portfolio_value: float,
        date: str = "",
    ) -> float:
        """Compute size and apply affordability cap. Returns filled size."""
        size = self._raw_size(entry, portfolio_value, entry_price, state, date)
        if size <= 0:
            return 0.0
        return self._apply_affordability_cap(state, entry, size, entry_price, date)

    # -- Raw sizing --------------------------------------------------------

    def _raw_size(
        self,
        entry: PendingEntry,
        portfolio_value: float,
        entry_price: float,
        state: SimulationState | None = None,
        date: str = "",
    ) -> float:
        """Compute position size before the affordability cap."""
        if entry.explicit_size and entry.position_size > 0:
            return float(entry.position_size)
        if entry.stop_price > 0:
            risk_amount = (
                portfolio_value
                * entry.risk_per_trade
                * self._config.risk_budget_multiplier()
            )
            risk_per_share = abs(entry_price - entry.stop_price)
            if risk_per_share > 0.001:
                return risk_amount / risk_per_share
            # Stop distance is too small for meaningful risk-based sizing;
            # emit a diagnostic so the operator knows we fell back.
            if state is not None:
                state.add_diagnostic(
                    "warning",
                    "stop_distance_too_small",
                    (
                        f"Stop distance {risk_per_share:.6f} is below the "
                        f"minimum threshold (0.001). Falling back to default "
                        f"position size of {_DEFAULT_POSITION_SIZE}."
                    ),
                    date=date,
                    metadata={"risk_per_share": risk_per_share},
                )
        return _DEFAULT_POSITION_SIZE  # no stop/explicit size

    # -- Affordability cap -------------------------------------------------

    def _apply_affordability_cap(
        self,
        state: SimulationState,
        entry: PendingEntry,
        size: float,
        price: float,
        date: str = "",
    ) -> float:
        """Cap position size to available margin / buying power."""
        if price <= 0 or self._config.allow_negative_cash:
            return size
        cap = self._max_affordable_size(state.cash, price)
        if cap <= 0:
            state.add_diagnostic(
                "order_rejected",
                "insufficient_cash",
                "Entry skipped because no buying power was available.",
                date=date,
            )
            return 0.0
        capped = min(size, cap)
        if capped >= size:
            return capped
        if entry.explicit_size:
            if self._config.reject_oversized_explicit_orders:
                state.add_diagnostic(
                    "order_rejected",
                    "explicit_size_rejected",
                    (
                        f"Explicit size {size:.8f} exceeds max "
                        f"affordable {cap:.8f}."
                    ),
                    date=date,
                    metadata={
                        "requested_size": size,
                        "max_affordable_size": cap,
                    },
                )
                return 0.0
            if not self._config.cap_explicit_size:
                # Allow full size through uncapped (documented behaviour).
                return size
        state.add_diagnostic(
            "order_resized",
            "affordability_cap",
            f"Requested size {size:.8f} capped to {capped:.8f}.",
            date=date,
            metadata={"requested_size": size, "filled_size": capped},
        )
        return capped

    def _max_affordable_size(self, cash: float, fill_price: float) -> float:
        """Maximum position size given equity, leverage, and entry cost.

        Commission is included in the effective price as a safety margin
        so the affordability cap cannot over-commit buying power when
        commission is significant (e.g. 1%+). At typical rates (0.1%)
        the impact is negligible.
        """
        if fill_price <= 0:
            return 0.0
        effective_price = fill_price * (1.0 + max(self._config.commission_pct, 0.0))
        if effective_price <= 0:
            return 0.0
        buying_power = cash * self._leverage.multiplier
        return max(0.0, buying_power / effective_price)
