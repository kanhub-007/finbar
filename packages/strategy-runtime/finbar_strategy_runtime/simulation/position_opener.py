"""PositionOpener — entry stop validation and position creation."""

from __future__ import annotations

import logging

from finbar_strategy_runtime.simulation.backtest_diagnostic import BacktestDiagnostic
from finbar_strategy_runtime.simulation.execution_config import ExecutionConfig
from finbar_strategy_runtime.simulation.leverage_config import LeverageConfig
from finbar_strategy_runtime.simulation.pending_entry import PendingEntry
from finbar_strategy_runtime.simulation.simulation_state import SimulationState
from finbar_strategy_runtime.simulation.simulated_position import SimulatedPosition
from finbar_strategy_runtime.simulation.margin_account_manager import (
    MarginAccountManager,
)
from finbar_strategy_runtime.simulation.position_closer import (
    _commission as _commission_shared,
)

logger = logging.getLogger(__name__)


class PositionOpener:
    """Validate entry conditions and create open positions."""

    def __init__(
        self,
        config: ExecutionConfig,
        margin_manager: MarginAccountManager | None = None,
    ) -> None:
        """Create an opener for one execution configuration.

        Args:
            config: Execution settings for this backtest run.
            margin_manager: Optional full-margin account manager. When set
                (margin_mode == "full"), entry cash movements are mirrored into
                the margin account and the position's initial margin is locked.
                When None (simplified mode), cash is tracked on ``state.cash``
                alone.
        """
        self._config = config
        self._leverage = LeverageConfig(
            multiplier=config.leverage_multiplier,
            maintenance_margin_pct=config.maintenance_margin_pct,
        )
        self._margin = margin_manager

    def bind_margin_manager(self, margin_manager: MarginAccountManager | None) -> None:
        """Attach (or detach) the full-margin account manager.

        The margin manager is bound lazily from ``PositionExecutor.setup_full_margin``
        because it needs the per-run ``initial_cash`` that is only known when
        ``BacktestRunner.run`` is called.
        """
        self._margin = margin_manager

    def open(
        self,
        state: SimulationState,
        entry: PendingEntry,
        size: float,
        raw_price: float,
        fill_price: float,
        date: str,
    ) -> None:
        """Create the position, update cash, margin, and position fields."""
        cost = size * fill_price
        commission = self._commission(cost)
        entry_slippage = abs(fill_price - raw_price) * size
        state.total_commission += commission
        state.total_slippage += entry_slippage

        cash_before = state.cash
        if entry.direction == "long":
            state.cash -= cost + commission
            if self._margin is not None:
                self._margin.lock_entry_margin(state, cost, commission)
            state.position = SimulatedPosition()
            state.position.size = size
            state.position.direction = "long"
        elif entry.direction == "short":
            state.cash += cost - commission
            if self._margin is not None:
                self._margin.credit_entry_short(state, cost, commission)
            state.position = SimulatedPosition()
            state.position.size = -size
            state.position.direction = "short"
        else:
            return

        state.position.entry_price = fill_price
        state.position.entry_date = date
        state.position.stop_price = entry.stop_price
        state.position.target_price = entry.target_price
        state.position.entry_commission = commission
        state.position.entry_slippage = entry_slippage
        state.position.liquidation_price = self._leverage.liquidation_price(
            fill_price, entry.direction
        )
        margin = self._leverage.margin_required(cost)
        state.used_margin += margin

        logger.info(
            "[ENTRY] %s | %s | price=%.2f size=%s cost=%.2f margin=%.2f | "
            "cash: %.2f->%.2f (d=%.2f) | stop=%.2f target=%.2f liq=%.2f",
            date,
            entry.direction.upper(),
            fill_price,
            size,
            cost,
            margin,
            cash_before,
            state.cash,
            state.cash - cash_before,
            entry.stop_price,
            entry.target_price,
            state.position.liquidation_price,
        )

    def stop_valid(self, entry: PendingEntry, price: float, date: str) -> bool:
        """Validate stop direction and (if leveraged) liquidation boundary."""
        if entry.stop_price <= 0:
            return True
        if entry.direction == "long" and entry.stop_price >= price:
            self._log_skip(date, entry, price, "stop above entry")
            return False
        if entry.direction == "short" and entry.stop_price <= price:
            self._log_skip(date, entry, price, "stop below entry")
            return False
        if not self._leverage.is_spot:
            liq = self._leverage.liquidation_price(price, entry.direction)
            if not self._leverage.validate_stop(
                entry.stop_price, price, entry.direction
            ):
                logger.warning(
                    "[ENTRY-SKIP] %s | %s | price=%.2f stop=%.2f "
                    "beyond liquidation=%.2f (L=%.0fx)",
                    date,
                    entry.direction.upper(),
                    price,
                    entry.stop_price,
                    liq,
                    self._leverage.multiplier,
                )
                return False
        return True

    def add_diagnostic(
        self,
        state: SimulationState,
        severity: str,
        code: str,
        date: str,
        message: str,
        extra: dict | None = None,
    ) -> None:
        """Append a structured diagnostic to loop state.

        Delegates to ``SimulationState.add_diagnostic`` so diagnostic shape
        (including the ``date`` field) is constructed in exactly one place.
        """
        state.add_diagnostic(
            severity=severity,
            code=code,
            message=message,
            date=date,
            metadata=extra,
        )

    # -- Cost helpers ---------------------------------------------------

    def _commission(self, gross: float) -> float:
        """Per-side commission (delegates to the shared helper)."""
        return _commission_shared(gross, self._config.commission_pct)

    @staticmethod
    def _log_skip(date: str, entry: PendingEntry, price: float, reason: str) -> None:
        logger.info(
            "[ENTRY-SKIP] %s | %s | price=%.2f stop=%.2f | %s",
            date,
            entry.direction.upper(),
            price,
            entry.stop_price,
            reason,
        )
