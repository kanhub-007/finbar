"""PositionCloser — exit settlement, margin release, borrow, and trade recording."""

from __future__ import annotations

import logging

from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.leverage_config import LeverageConfig
from finbar.core.domain.entities.trade_record import TradeRecord
from finbar.infrastructure.services.backtest_loop_state import BacktestLoopState

logger = logging.getLogger(__name__)


class PositionCloser:
    """Close positions, settle cash, release margin, and record trades."""

    def __init__(self, config: ExecutionConfig) -> None:
        """Create a closer bound to one execution configuration."""
        self._config = config
        self._leverage = LeverageConfig(multiplier=config.leverage_multiplier)

    # -- Public API -----------------------------------------------------

    def check_liquidation(
        self,
        state: BacktestLoopState,
        high: float,
        low: float,
        date: str,
        on_liquidated,
    ) -> bool:
        """Check and execute liquidation if price crosses the boundary.

        Calls `on_liquidated(state, liq_price, date, reason)` when tripped.
        Returns True when liquidation occurred.
        """
        if self._leverage.is_spot or state.position.size == 0:
            return False
        liq = state.position.liquidation_price
        if state.position.size > 0 and low <= liq:
            on_liquidated(state, liq, date, "liquidation")
            return True
        if state.position.size < 0 and high >= liq:
            on_liquidated(state, liq, date, "liquidation")
            return True
        return False

    def release_margin(
        self, state: BacktestLoopState, abs_size: float, entry_price: float
    ) -> None:
        """Release margin for a closed position."""
        if not self._leverage.is_spot and entry_price > 0:
            released = self._leverage.margin_required(abs_size * entry_price)
            state.used_margin = max(0.0, state.used_margin - released)

    def borrow_cost(
        self,
        abs_size: float,
        entry_price: float,
        direction: str,
        entry_date: str,
        exit_date: str,
    ) -> float:
        """Compute borrow cost for short positions (simplified)."""
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

    def build_trade(
        self,
        *,
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
    ) -> TradeRecord:
        """Assemble an immutable TradeRecord from exit-time values."""
        return TradeRecord(
            entry_date=entry_date,
            exit_date=exit_date,
            entry_price=entry_price,
            exit_price=exit_price,
            size=abs_size,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            entry_commission=entry_commission,
            exit_commission=exit_commission,
            borrow_cost=borrow_cost,
            total_commission=entry_commission + exit_commission,
            pnl_pct=(
                net_pnl / (entry_price * abs_size)
                if entry_price > 0 and abs_size > 0
                else 0.0
            ),
            duration_bars=state.position.bars_held,
            direction=direction,
            exit_reason=exit_reason,
        )

    # -- Pure static helpers --------------------------------------------

    @staticmethod
    def calc_pnl(
        size: float, entry_price: float, exit_price: float, abs_size: float
    ) -> float:
        """Gross PnL from price movement only."""
        if size > 0:
            return (exit_price - entry_price) * abs_size
        return (entry_price - exit_price) * abs_size

    @staticmethod
    def cash_settlement(
        size: float,
        fill_cost: float,
        commission: float,
        borrow_cost: float = 0.0,
    ) -> float:
        """Net cash change at exit."""
        if size > 0:
            return fill_cost - commission
        return -(fill_cost + commission + borrow_cost)


# -- Module-level helpers -----------------------------------------------


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
