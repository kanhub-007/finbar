"""PositionExecutor — entry, exit, stop/target, cost, and sizing logic.

All position-mutation functions live here. The executor is instantiated
per run with cost parameters so the bar loop does not need to thread
commission and slippage through every call site.
"""

from __future__ import annotations

import logging

from finbar.core.domain.entities.pending_entry import PendingEntry
from finbar.infrastructure.services.backtest_loop_state import BacktestLoopState
from finbar.infrastructure.services.backtest_position import BacktestPosition

logger = logging.getLogger(__name__)

_DEFAULT_POSITION_SIZE = 100


class PositionExecutor:
    """Handle position lifecycle: enter, exit, stop/target, and liquidation."""

    def __init__(
        self,
        commission_pct: float = 0.0,
        slippage_pct: float = 0.0,
    ):
        """Create an executor with per-run cost settings."""
        self._commission_pct = commission_pct
        self._slippage_pct = slippage_pct

    # -- Public API used by the bar loop --------------------------------

    def enter(
        self,
        state: BacktestLoopState,
        entry: PendingEntry,
        price: float,
        date: str,
    ) -> None:
        """Enter a new position from a pending entry signal."""
        if not self._protective_stop_valid(entry, price):
            logger.info(
                "[ENTRY-SKIP] %s | %s | price=%.2f invalid stop=%.2f",
                date,
                entry.direction.upper(),
                price,
                entry.stop_price,
            )
            return

        size = self._resolve_size(entry, price, self._portfolio_value(state, price))
        if size <= 0:
            return

        cash_before = state.cash
        if not entry.explicit_size and entry.direction == "long" and price > 0:
            max_affordable = int(state.cash / price) if state.cash > 0 else 0
            if max_affordable <= 0:
                return
            size = min(size, max_affordable)

        fill_price = self._apply_slippage(price, entry.direction, "entry")
        cost = size * fill_price
        commission = self._commission(cost)
        state.total_commission += commission
        state.total_slippage += abs(fill_price - price) * size

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
        logger.info(
            "[ENTRY] %s | %s | price=%.2f size=%s cost=%.2f | "
            "cash: %.2f->%.2f (d=%.2f) | stop=%.2f target=%.2f",
            date,
            entry.direction.upper(),
            fill_price,
            size,
            cost,
            cash_before,
            state.cash,
            state.cash - cash_before,
            entry.stop_price,
            entry.target_price,
        )

    def exit_position(
        self,
        state: BacktestLoopState,
        exit_price: float,
        bar_date: str,
        exit_reason: str = "signal",
    ) -> None:
        """Close the current position and record the trade."""
        abs_size = abs(state.position.size)
        cash_before = state.cash
        entry_price = state.position.entry_price
        entry_date = state.position.entry_date
        direction = state.position.direction

        fill_price = self._apply_slippage(exit_price, direction, "exit")
        fill_cost = abs_size * fill_price
        commission = self._commission(fill_cost)
        state.total_commission += commission
        state.total_slippage += abs(fill_price - exit_price) * abs_size

        if state.position.size > 0:
            pnl = (fill_price - entry_price) * abs_size
            state.cash += fill_cost - commission
        else:
            pnl = (entry_price - fill_price) * abs_size
            state.cash -= fill_cost + commission

        pnl_pct = (
            pnl / (entry_price * abs_size) if entry_price > 0 and abs_size > 0 else 0.0
        )
        state.trades.append(
            {
                "entry_date": entry_date,
                "exit_date": bar_date,
                "entry_price": entry_price,
                "exit_price": fill_price,
                "size": abs_size,
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 4),
                "duration_bars": state.position.bars_held,
                "metadata": {"direction": direction, "exit_reason": exit_reason},
            }
        )
        logger.info(
            "[EXIT]  %s | %s | exit=%.2f entry=%.2f size=%s | "
            "PnL=%.2f (%.2f%%) | cash: %.2f->%.2f (d=%.2f) | "
            "bars=%d reason=%s",
            bar_date,
            direction.upper(),
            exit_price,
            entry_price,
            abs_size,
            pnl,
            pnl_pct * 100,
            cash_before,
            state.cash,
            state.cash - cash_before,
            state.position.bars_held,
            exit_reason,
        )
        state.position.reset()

    def check_exit_conditions(
        self,
        state: BacktestLoopState,
        open_price: float,
        high: float,
        low: float,
        bar_date: str,
    ) -> None:
        """Check gap-aware stop-loss and take-profit for the open position."""
        state.position.bars_held += 1
        fill = self._resolve_intrabar_exit(state.position, open_price, high, low)
        if fill is not None:
            exit_price, reason = fill
            self.exit_position(state, exit_price, bar_date, exit_reason=reason)

    def liquidate_open(
        self,
        state: BacktestLoopState,
        final_close: float,
        final_date: str,
    ) -> None:
        """Close any open position at the final bar close."""
        if state.position.size == 0 or not final_date:
            return
        self.exit_position(
            state, final_close, final_date, exit_reason="end_of_backtest"
        )
        if state.equity_curve:
            last = state.equity_curve[-1]
            last["value"] = self._portfolio_value(state, final_close)
            last["position"] = 0
            if last["value"] > state.peak_value:
                state.peak_value = last["value"]
            last["drawdown"] = (
                (state.peak_value - last["value"]) / state.peak_value
                if state.peak_value > 0
                else 0.0
            )

    @staticmethod
    def portfolio_value(state: BacktestLoopState, close: float) -> float:
        return PositionExecutor._portfolio_value(state, close)

    # -- Private helpers -------------------------------------------------

    @staticmethod
    def _portfolio_value(state: BacktestLoopState, close: float) -> float:
        """Calculate current portfolio value."""
        if state.position.size > 0:
            return state.cash + state.position.size * close
        if state.position.size < 0:
            return state.cash - abs(state.position.size) * close
        return state.cash

    @staticmethod
    def _protective_stop_valid(entry: PendingEntry, entry_price: float) -> bool:
        if entry.stop_price <= 0:
            return True
        if entry.direction == "long":
            return entry.stop_price < entry_price
        if entry.direction == "short":
            return entry.stop_price > entry_price
        return False

    @staticmethod
    def _resolve_size(
        entry: PendingEntry,
        entry_price: float,
        portfolio_value: float,
    ) -> int:
        if entry.explicit_size and entry.position_size > 0:
            return entry.position_size
        if entry.stop_price > 0:
            risk_amount = portfolio_value * entry.risk_per_trade
            risk_per_share = abs(entry_price - entry.stop_price)
            if risk_per_share > 0.001:
                return max(1, int(risk_amount / risk_per_share))
        return _DEFAULT_POSITION_SIZE

    def _apply_slippage(
        self,
        price: float,
        direction: str,
        side: str,
    ) -> float:
        if self._slippage_pct <= 0:
            return price
        if direction == "long":
            factor = (
                1.0 + self._slippage_pct
                if side == "entry"
                else 1.0 - self._slippage_pct
            )
        elif direction == "short":
            factor = (
                1.0 - self._slippage_pct
                if side == "entry"
                else 1.0 + self._slippage_pct
            )
        else:
            return price
        return price * factor

    def _commission(self, gross: float) -> float:
        if self._commission_pct <= 0:
            return 0.0
        return abs(gross) * self._commission_pct

    @staticmethod
    def _resolve_intrabar_exit(
        position: BacktestPosition,
        open_price: float,
        high: float,
        low: float,
    ) -> tuple[float, str] | None:
        stop = position.stop_price
        target = position.target_price
        if position.size > 0:
            return PositionExecutor._resolve_long_exit(
                open_price, high, low, stop, target
            )
        if position.size < 0:
            return PositionExecutor._resolve_short_exit(
                open_price, high, low, stop, target
            )
        return None

    @staticmethod
    def _resolve_long_exit(
        open_price: float,
        high: float,
        low: float,
        stop: float,
        target: float,
    ) -> tuple[float, str] | None:
        if stop > 0 and open_price <= stop:
            return open_price, "stop_loss_gap"
        if target > 0 and open_price >= target:
            return open_price, "take_profit_gap"
        stop_hit = stop > 0 and low <= stop
        target_hit = target > 0 and high >= target
        if stop_hit:
            return stop, "stop_loss"
        if target_hit:
            return target, "take_profit"
        return None

    @staticmethod
    def _resolve_short_exit(
        open_price: float,
        high: float,
        low: float,
        stop: float,
        target: float,
    ) -> tuple[float, str] | None:
        if stop > 0 and open_price >= stop:
            return open_price, "stop_loss_gap"
        if target > 0 and open_price <= target:
            return open_price, "take_profit_gap"
        stop_hit = stop > 0 and high >= stop
        target_hit = target > 0 and low <= target
        if stop_hit:
            return stop, "stop_loss"
        if target_hit:
            return target, "take_profit"
        return None
