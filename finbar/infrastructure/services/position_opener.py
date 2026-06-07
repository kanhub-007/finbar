"""PositionOpener — entry stop validation and position creation."""

from __future__ import annotations

import logging

from finbar.core.domain.entities.backtest_diagnostic import BacktestDiagnostic
from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.leverage_config import LeverageConfig
from finbar.core.domain.entities.pending_entry import PendingEntry
from finbar.infrastructure.services.backtest_loop_state import BacktestLoopState
from finbar.infrastructure.services.backtest_position import BacktestPosition

logger = logging.getLogger(__name__)


class PositionOpener:
    """Validate entry conditions and create open positions."""

    def __init__(self, config: ExecutionConfig) -> None:
        """Create an opener for one execution configuration."""
        self._config = config
        self._leverage = LeverageConfig(multiplier=config.leverage_multiplier)

    def open(
        self,
        state: BacktestLoopState,
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
            state.position = BacktestPosition()
            state.position.size = size
            state.position.direction = "long"
        elif entry.direction == "short":
            state.cash += cost - commission
            state.position = BacktestPosition()
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
        state: BacktestLoopState,
        severity: str,
        code: str,
        date: str,
        message: str,
        extra: dict | None = None,
    ) -> None:
        """Append a structured diagnostic to loop state."""
        state.diagnostics.append(
            BacktestDiagnostic(
                severity=severity,
                code=code,
                date=date,
                message=message,
                metadata=extra or {},
            )
        )

    # -- Cost helpers ---------------------------------------------------

    def _commission(self, gross: float) -> float:
        if self._config.commission_pct <= 0:
            return 0.0
        return abs(gross) * self._config.commission_pct

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
