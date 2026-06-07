"""PositionExecutor — entry, exit, stop/target, cost, and margin logic.

Facade that delegates to PositionSizer, PositionOpener, PositionCloser,
and IntrabarExitResolver. The bar loop calls the four public methods;
internal mechanics are composed from smaller, independently testable units.
"""

from __future__ import annotations

import logging

from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.pending_entry import PendingEntry
from finbar.infrastructure.services.backtest_loop_state import BacktestLoopState
from finbar.infrastructure.services.intrabar_exit_resolver import (
    IntrabarExitResolver,
)
from finbar.infrastructure.services.margin_account_manager import (
    MarginAccountManager,
)
from finbar.infrastructure.services.position_closer import PositionCloser
from finbar.infrastructure.services.position_opener import PositionOpener
from finbar.infrastructure.services.position_sizer import PositionSizer

logger = logging.getLogger(__name__)


class PositionExecutor:
    """Handle position lifecycle: enter, exit, stop/target, and liquidation.

    Composes:
      - PositionSizer     for sizing and affordability caps
      - PositionOpener    for entry validation and position creation
      - PositionCloser    for exit settlement, margin, borrow, trade records
      - IntrabarExitResolver for gap-aware stop/target logic
    """

    def __init__(self, execution_config: ExecutionConfig | None = None) -> None:
        """Create an executor with per-run execution settings."""
        config = execution_config or ExecutionConfig()
        self._config = config
        self._sizer = PositionSizer(config)
        self._opener = PositionOpener(config)
        self._closer = PositionCloser(config)
        self._slippage_pct = config.slippage_pct
        self._commission_pct = config.commission_pct
        self._full_margin = config.margin_mode == "full"
        self._margin: MarginAccountManager | None = None

    # -- Public API used by the bar loop --------------------------------

    def setup_full_margin(self, initial_cash: float) -> None:
        """Initialize margin account for full-margin mode.

        No-op in simplified mode.
        """
        if self._full_margin:
            self._margin = MarginAccountManager(self._config, initial_cash)
            self._margin.sync_state_equity(None)  # pending first sync in loop

    def sync_margin_equity(self, state: BacktestLoopState) -> None:
        """Sync BacktestLoopState.cash to margin account equity.

        No-op in simplified mode.
        """
        if self._full_margin and self._margin:
            self._margin.sync_state_equity(state)

    def apply_funding(self, state: BacktestLoopState) -> None:
        """Apply per-bar funding payment to open position.

        No-op when funding is disabled or in simplified mode.
        """
        if self._full_margin and self._margin:
            self._margin.apply_funding(state.position)

    def check_margin_call(self, state: BacktestLoopState, close: float) -> None:
        """Check margin call status and liquidate if needed.

        No-op in simplified mode.
        """
        if not self._full_margin or self._margin is None:
            return
        result = self._margin.check_margin_call(state.position, close)
        if result == "liquidation":
            self.exit_position(state, close, "", exit_reason="margin_call")

    def enter(
        self,
        state: BacktestLoopState,
        entry: PendingEntry,
        price: float,
        date: str,
    ) -> None:
        """Enter a new position from a pending entry signal."""
        fill_price = self._apply_slippage(price, entry.direction, "entry")
        if not self._opener.stop_valid(entry, fill_price, date):
            return
        portfolio = self._portfolio_value(state, fill_price)
        size = self._sizer.resolve(state, entry, fill_price, portfolio)
        if size <= 0:
            self._opener.add_diagnostic(
                state,
                "order_rejected",
                "entry_size_zero",
                date,
                "Entry skipped because resolved position size was zero.",
            )
            return
        self._opener.open(state, entry, size, price, fill_price, date)

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

        gross_pnl = self._closer.calc_pnl(
            state.position.size, entry_price, fill_price, abs_size
        )
        entry_commission = state.position.entry_commission
        borrow = self._closer.borrow_cost(
            abs_size, entry_price, direction, entry_date, bar_date
        )
        net_pnl = gross_pnl - entry_commission - commission - borrow
        state.total_borrow_cost += borrow
        state.cash += self._closer.cash_settlement(
            state.position.size, fill_cost, commission, borrow
        )
        self._closer.release_margin(state, abs_size, entry_price)

        trade = self._closer.build_trade(
            state=state,
            entry_date=entry_date,
            exit_date=bar_date,
            entry_price=entry_price,
            exit_price=fill_price,
            abs_size=abs_size,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            entry_commission=entry_commission,
            exit_commission=commission,
            borrow_cost=borrow,
            direction=direction,
            exit_reason=exit_reason,
        )
        state.trades.append(trade.to_dict())
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
            borrow,
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

        liquidated = self._closer.check_liquidation(
            state, high, low, bar_date, self._on_liquidated
        )
        if liquidated:
            return

        fill = IntrabarExitResolver.resolve(state.position, open_price, high, low)
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

    # -- Private: callbacks and helpers ---------------------------------

    def _on_liquidated(
        self,
        state: BacktestLoopState,
        price: float,
        date: str,
        reason: str,
    ) -> None:
        """Callback invoked by the closer when liquidation is triggered."""
        self.exit_position(state, price, date, exit_reason=reason)

    @staticmethod
    def _portfolio_value(state: BacktestLoopState, close: float) -> float:
        """Calculate current portfolio value."""
        if state.position.size > 0:
            return state.cash + state.position.size * close
        if state.position.size < 0:
            return state.cash - abs(state.position.size) * close
        return state.cash

    def _apply_slippage(self, price: float, direction: str, side: str) -> float:
        if self._slippage_pct <= 0:
            return price
        factor = {
            ("long", "entry"): 1.0 + self._slippage_pct,
            ("long", "exit"): 1.0 - self._slippage_pct,
            ("short", "entry"): 1.0 - self._slippage_pct,
            ("short", "exit"): 1.0 + self._slippage_pct,
        }.get((direction, side), 1.0)
        return price * factor

    def _commission(self, gross: float) -> float:
        if self._commission_pct <= 0:
            return 0.0
        return abs(gross) * self._commission_pct
