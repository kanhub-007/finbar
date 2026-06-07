"""PositionExecutor — entry, exit, stop/target, cost, margin, and sizing logic.

All position-mutation functions live here. The executor is instantiated
per run with cost and leverage parameters so the bar loop does not need
to thread commission, slippage, and margin through every call site.
"""

from __future__ import annotations

import logging

from finbar.core.domain.entities.backtest_diagnostic import BacktestDiagnostic
from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.leverage_config import LeverageConfig
from finbar.core.domain.entities.pending_entry import PendingEntry
from finbar.infrastructure.services.backtest_loop_state import BacktestLoopState
from finbar.infrastructure.services.backtest_position import BacktestPosition

logger = logging.getLogger(__name__)

_DEFAULT_POSITION_SIZE = 100.0


class PositionExecutor:
    """Handle position lifecycle: enter, exit, stop/target, and liquidation."""

    def __init__(
        self,
        commission_pct: float = 0.0,
        slippage_pct: float = 0.0,
        leverage: LeverageConfig | None = None,
        execution_config: ExecutionConfig | None = None,
    ):
        """Create an executor with per-run cost and leverage settings."""
        leverage_multiplier = leverage.multiplier if leverage is not None else 1.0
        self._config = execution_config or ExecutionConfig(
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
            leverage_multiplier=leverage_multiplier,
        )
        self._commission_pct = self._config.commission_pct
        self._slippage_pct = self._config.slippage_pct
        self._leverage = LeverageConfig(multiplier=self._config.leverage_multiplier)

    # -- Public API used by the bar loop --------------------------------

    def enter(
        self,
        state: BacktestLoopState,
        entry: PendingEntry,
        price: float,
        date: str,
    ) -> None:
        """Enter a new position from a pending entry signal."""
        fill_price = self._apply_slippage(price, entry.direction, "entry")
        if not self._entry_stop_valid(entry, fill_price, date):
            return
        size = self._resolve_entry_size(state, entry, fill_price)
        if size <= 0:
            self._add_diagnostic(
                state,
                "order_rejected",
                "entry_size_zero",
                date,
                "Entry skipped because resolved position size was zero.",
            )
            return
        self._open_position(state, entry, size, price, fill_price, date)

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

        gross_pnl = self._calc_pnl(
            state.position.size, entry_price, fill_price, abs_size
        )
        entry_commission = state.position.entry_commission
        borrow_cost = self._borrow_cost(
            abs_size,
            entry_price,
            direction,
            entry_date,
            bar_date,
        )
        net_pnl = gross_pnl - entry_commission - commission - borrow_cost
        state.total_borrow_cost += borrow_cost
        state.cash += self._cash_settlement(
            state.position.size, fill_cost, commission, borrow_cost
        )
        self._release_margin(state, abs_size, entry_price)
        self._record_trade(
            state,
            entry_date,
            bar_date,
            entry_price,
            fill_price,
            abs_size,
            gross_pnl,
            net_pnl,
            entry_commission,
            commission,
            borrow_cost,
            direction,
            exit_reason,
        )
        logger.info(
            "[EXIT]  %s | %s | exit=%.2f entry=%.2f size=%s | "
            "NetPnL=%.2f GrossPnL=%.2f (%.2f%%) | "
            "cash: %.2f->%.2f (d=%.2f) | bars=%d reason=%s margin=%.2f "
            "borrow=%.2f",
            bar_date,
            direction.upper(),
            exit_price,
            entry_price,
            abs_size,
            net_pnl,
            gross_pnl,
            (net_pnl / (entry_price * abs_size) * 100) if entry_price > 0 else 0,
            cash_before,
            state.cash,
            state.cash - cash_before,
            state.position.bars_held,
            exit_reason,
            state.used_margin,
            borrow_cost,
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
        """Check stop-loss, take-profit, and liquidation for the open position."""
        state.position.bars_held += 1

        if self._check_liquidation(state, high, low, bar_date):
            return

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

    # -- Private: entry helpers -----------------------------------------

    def _entry_stop_valid(self, entry: PendingEntry, price: float, date: str) -> bool:
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

    def _resolve_entry_size(
        self, state: BacktestLoopState, entry: PendingEntry, price: float
    ) -> float:
        """Compute position size and apply affordability cap."""
        portfolio = self._portfolio_value(state, price)
        size = self._calc_risk_size(entry, portfolio, price)
        if size <= 0:
            return 0.0
        return self._apply_affordability_cap(state, entry, size, price)

    def _calc_risk_size(
        self, entry: PendingEntry, portfolio_value: float, entry_price: float
    ) -> float:
        """Size position based on risk budget."""
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
        return _DEFAULT_POSITION_SIZE

    def _apply_affordability_cap(
        self,
        state: BacktestLoopState,
        entry: PendingEntry,
        size: float,
        price: float,
    ) -> float:
        """Cap position size to available margin / buying power."""
        if price <= 0 or self._config.allow_negative_cash:
            return size
        cap = self._max_affordable_size(state.cash, price)
        if cap <= 0:
            self._add_diagnostic(
                state,
                "order_rejected",
                "insufficient_cash",
                "",
                "Entry skipped because no buying power was available.",
            )
            return 0.0
        capped = min(size, cap)
        if capped >= size:
            return capped
        if entry.explicit_size and self._should_reject_oversized_explicit_order():
            self._add_diagnostic(
                state,
                "order_rejected",
                "explicit_size_rejected",
                "",
                f"Explicit size {size:.8f} exceeds max affordable {cap:.8f}.",
                {"requested_size": size, "max_affordable_size": cap},
            )
            return 0.0
        self._add_diagnostic(
            state,
            "order_resized",
            "affordability_cap",
            "",
            f"Requested size {size:.8f} capped to {capped:.8f}.",
            {"requested_size": size, "filled_size": capped},
        )
        return capped

    def _open_position(
        self,
        state: BacktestLoopState,
        entry: PendingEntry,
        size: float,
        raw_price: float,
        fill_price: float,
        date: str,
    ) -> None:
        """Create the position, update cash and margin."""
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

    # -- Private: exit helpers ------------------------------------------

    def _check_liquidation(
        self, state: BacktestLoopState, high: float, low: float, date: str
    ) -> bool:
        """Check and execute liquidation if price crosses the boundary.
        Returns True when liquidation occurred."""
        if self._leverage.is_spot or state.position.size == 0:
            return False
        liq = state.position.liquidation_price
        if state.position.size > 0 and low <= liq:
            self.exit_position(state, liq, date, exit_reason="liquidation")
            return True
        if state.position.size < 0 and high >= liq:
            self.exit_position(state, liq, date, exit_reason="liquidation")
            return True
        return False

    @staticmethod
    def _calc_pnl(
        size: float, entry_price: float, exit_price: float, abs_size: float
    ) -> float:
        if size > 0:
            return (exit_price - entry_price) * abs_size
        return (entry_price - exit_price) * abs_size

    @staticmethod
    def _cash_settlement(
        size: float,
        fill_cost: float,
        commission: float,
        borrow_cost: float = 0.0,
    ) -> float:
        if size > 0:
            return fill_cost - commission
        return -(fill_cost + commission + borrow_cost)

    def _release_margin(
        self, state: BacktestLoopState, abs_size: float, entry_price: float
    ) -> None:
        if not self._leverage.is_spot and entry_price > 0:
            released = self._leverage.margin_required(abs_size * entry_price)
            state.used_margin = max(0.0, state.used_margin - released)

    @staticmethod
    def _record_trade(
        state: BacktestLoopState,
        entry_date: str,
        exit_date: str,
        entry_price: float,
        exit_price: float,
        abs_size: float,
        gross_pnl: float,
        net_pnl: float,
        entry_commission: float,
        exit_commission: float,
        borrow_cost: float,
        direction: str,
        exit_reason: str,
    ) -> None:
        pnl_pct = (
            net_pnl / (entry_price * abs_size)
            if entry_price > 0 and abs_size > 0
            else 0.0
        )
        total_commission = entry_commission + exit_commission
        state.trades.append(
            {
                "entry_date": entry_date,
                "exit_date": exit_date,
                "entry_price": round(entry_price, 8),
                "exit_price": round(exit_price, 8),
                "size": abs_size,
                "pnl": round(net_pnl, 2),
                "net_pnl": round(net_pnl, 2),
                "gross_pnl": round(gross_pnl, 2),
                "entry_commission": round(entry_commission, 2),
                "exit_commission": round(exit_commission, 2),
                "borrow_cost": round(borrow_cost, 2),
                "total_commission": round(total_commission, 2),
                "pnl_pct": round(pnl_pct, 4),
                "duration_bars": state.position.bars_held,
                "metadata": {"direction": direction, "exit_reason": exit_reason},
            }
        )

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

    # -- Private: portfolio / cost helpers ------------------------------

    @staticmethod
    def _portfolio_value(state: BacktestLoopState, close: float) -> float:
        """Calculate current portfolio value."""
        if state.position.size > 0:
            return state.cash + state.position.size * close
        if state.position.size < 0:
            return state.cash - abs(state.position.size) * close
        return state.cash

    def _apply_slippage(
        self,
        price: float,
        direction: str,
        side: str,
    ) -> float:
        if self._slippage_pct <= 0:
            return price
        factor = {
            ("long", "entry"): 1.0 + self._slippage_pct,
            ("long", "exit"): 1.0 - self._slippage_pct,
            ("short", "entry"): 1.0 - self._slippage_pct,
            ("short", "exit"): 1.0 + self._slippage_pct,
        }.get((direction, side), 1.0)
        return price * factor

    def _max_affordable_size(self, cash: float, fill_price: float) -> float:
        """Return max size after accounting for leverage and entry commission."""
        if fill_price <= 0:
            return 0.0
        effective_price = fill_price * (1.0 + max(self._commission_pct, 0.0))
        if effective_price <= 0:
            return 0.0
        buying_power = cash * self._leverage.multiplier
        return max(0.0, buying_power / effective_price)

    def _commission(self, gross: float) -> float:
        if self._commission_pct <= 0:
            return 0.0
        return abs(gross) * self._commission_pct

    def _should_reject_oversized_explicit_order(self) -> bool:
        """Return True when oversized explicit orders should be rejected."""
        return (
            self._config.reject_oversized_explicit_orders
            or not self._config.cap_explicit_size
        )

    def _borrow_cost(
        self,
        abs_size: float,
        entry_price: float,
        direction: str,
        entry_date: str,
        exit_date: str,
    ) -> float:
        """Compute borrow cost for short positions."""
        if (
            direction != "short"
            or self._config.borrow_fee_annual_pct <= 0
            or abs_size <= 0
            or entry_price <= 0
        ):
            return 0.0
        days = _days_held(entry_date, exit_date)
        notional = abs_size * entry_price
        return notional * self._config.borrow_fee_annual_pct * (days / 365.0)

    @staticmethod
    def _add_diagnostic(
        state: BacktestLoopState,
        severity: str,
        code: str,
        date: str,
        message: str,
        extra: dict | None = None,
    ) -> None:
        """Append a structured backtest diagnostic to loop state."""
        state.diagnostics.append(
            BacktestDiagnostic(
                severity=severity,
                code=code,
                date=date,
                message=message,
                metadata=extra or {},
            )
        )

    # -- Private: intrabar exit resolution ------------------------------

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
        if stop > 0 and low <= stop:
            return stop, "stop_loss"
        if target > 0 and high >= target:
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
        if stop > 0 and high >= stop:
            return stop, "stop_loss"
        if target > 0 and low <= target:
            return target, "take_profit"
        return None


def _days_held(entry_date: str, exit_date: str) -> float:
    """Return the number of calendar days between two ISO date strings."""
    try:
        entry = _parse_date(entry_date)
        exit_ = _parse_date(exit_date)
        return max(0.0, (exit_ - entry).total_seconds() / 86400.0)
    except (ValueError, TypeError, OSError):
        return 0.0


def _parse_date(raw: str):
    """Parse a YYYY-MM-DD or ISO datetime string to a naive date."""
    from datetime import datetime

    raw = raw.strip()[:10]
    return datetime.strptime(raw, "%Y-%m-%d")
