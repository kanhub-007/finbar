"""PositionCloser — exit settlement, margin release, borrow, and trade recording."""

from __future__ import annotations

import logging

from finbar_strategy_runtime.simulation.execution_config import ExecutionConfig
from finbar_strategy_runtime.simulation.leverage_config import LeverageConfig
from finbar_strategy_runtime.simulation.simulation_state import SimulationState
from finbar_strategy_runtime.simulation.trade_record import TradeRecord

logger = logging.getLogger(__name__)


class PositionCloser:
    """Close positions, settle cash, release margin, and record trades."""

    def __init__(self, config: ExecutionConfig) -> None:
        """Create a closer bound to one execution configuration."""
        self._config = config
        self._leverage = LeverageConfig(
            multiplier=config.leverage_multiplier,
            maintenance_margin_pct=config.maintenance_margin_pct,
        )

    # -- Public API -----------------------------------------------------

    def close(
        self,
        state: SimulationState,
        exit_price: float,
        bar_date: str,
        exit_reason: str,
        *,
        slippage_pct: float,
        commission_pct: float,
        margin_manager=None,
    ) -> None:
        """Close the open position: settle cash, margin, borrow, record trade.

        Owns the full exit settlement (Moved Method — previously inlined in
        ``PositionExecutor.exit_position``, which was a Feature-Envy god
        method reading 8 fields off ``state.position``). The executor now
        delegates here and stays a thin Facade.

        Args:
            state: Mutable backtest state (position, cash, totals, trades).
            exit_price: Raw exit price before slippage.
            bar_date: Bar timestamp for the trade record / borrow calc.
            exit_reason: Machine-readable reason ("signal", "stop_loss", …).
            slippage_pct: Directional slippage fraction applied to the fill.
            commission_pct: Per-side commission fraction of fill cost.
            margin_manager: Optional full-margin account manager.
        """
        position = state.position
        abs_size = abs(position.size)
        cash_before = state.cash
        entry_price = position.entry_price
        entry_date = position.entry_date
        direction = position.direction

        fill_price = _apply_slippage(exit_price, direction, "exit", slippage_pct)
        fill_cost = abs_size * fill_price
        commission = _commission(fill_cost, commission_pct)
        state.total_commission += commission
        state.total_slippage += abs(fill_price - exit_price) * abs_size

        gross_pnl = self.calc_pnl(position.size, entry_price, fill_price, abs_size)
        entry_commission = position.entry_commission
        borrow = self.borrow_cost(
            abs_size, entry_price, direction, entry_date, bar_date
        )
        net_pnl = gross_pnl - entry_commission - commission - borrow
        state.total_borrow_cost += borrow
        state.cash += self.cash_settlement(
            position.size, fill_cost, commission, borrow
        )
        self.release_margin(state, abs_size, entry_price)
        if margin_manager is not None:
            margin_manager.settle_exit(
                state,
                fill_cost,
                commission,
                abs_size,
                entry_price,
                direction,
                borrow,
            )

        trade = self.build_trade(
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
            position.bars_held,
            exit_reason,
            state.used_margin,
            borrow,
        )
        position.reset()

    def check_liquidation(
        self,
        state: SimulationState,
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
        self, state: SimulationState, abs_size: float, entry_price: float
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
        """Compute borrow cost for short positions.

        Uses calendar-day granularity by default (``borrow_time_basis ==
        "calendar_day"``). When ``borrow_time_basis == "timestamp_delta"``,
        the full ISO timestamp is used so intraday holds accrue proportional
        borrow cost.
        """
        if (
            direction != "short"
            or self._config.borrow_fee_annual_pct <= 0
            or abs_size <= 0
            or entry_price <= 0
        ):
            return 0.0
        try:
            days = _time_held(
                entry_date, exit_date, self._config.borrow_time_basis
            )
        except (ValueError, TypeError, OSError):
            logger.warning(
                "Could not compute borrow holding period from dates: "
                "entry=%r exit=%r — borrow cost set to 0.0",
                entry_date,
                exit_date,
            )
            return 0.0
        notional = abs_size * entry_price
        return notional * self._config.borrow_fee_annual_pct * (days / 365.0)

    def build_trade(
        self,
        *,
        state: SimulationState,
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


def _time_held(entry_date: str, exit_date: str, time_basis: str) -> float:
    """Return the holding period in days (365-day year).

    ``calendar_day`` truncates ISO timestamps to their date component, so
    intraday same-day positions report zero days. ``timestamp_delta`` uses
    the full timestamp, so hourly positions accrue proportional borrow.

    Raises ValueError when a timestamp cannot be parsed, so the caller
    gets a clear diagnostic rather than a silently-zero borrow cost.
    """
    entry = _parse_timestamp(entry_date, time_basis)
    exit_ = _parse_timestamp(exit_date, time_basis)
    return max(0.0, (exit_ - entry).total_seconds() / 86400.0)


def _parse_timestamp(raw: str, time_basis: str):
    """Parse an ISO date or datetime string.

    ``calendar_day`` truncates to the first 10 characters (YYYY-MM-DD).
    ``timestamp_delta`` uses the full string.

    Raises ValueError when the string cannot be parsed as an ISO
    date/datetime, so callers get a clear diagnostic rather than a
    silently-zero borrow cost.
    """
    from datetime import datetime

    raw = raw.strip()
    # Normalise the "Z" UTC suffix so fromisoformat works on Python < 3.11.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    if time_basis == "calendar_day":
        # Validate that we have at least a full date (YYYY-MM-DD, 10 chars)
        # before slicing, so short strings raise instead of silently
        # producing zero borrow cost.
        if len(raw) < 10:
            raise ValueError(
                f"Timestamp too short for calendar_day parsing: {raw!r}"
            )
        raw = raw[:10]
    return datetime.fromisoformat(raw)


# Multiplicative sign per (direction, side): entry longens and exit shortens
# for longs; the reverse for shorts. Module-level so the table is built once.
_SLIPPAGE_SIGN: dict[tuple[str, str], float] = {
    ("long", "entry"): 1.0,
    ("long", "exit"): -1.0,
    ("short", "entry"): -1.0,
    ("short", "exit"): 1.0,
}


def _apply_slippage(
    price: float, direction: str, side: str, slippage_pct: float
) -> float:
    """Apply directional slippage to *price* for one fill.

    Single source of truth for slippage (used by both the closer and the
    executor), replacing the duplicated per-class logic.
    """
    if slippage_pct <= 0:
        return price
    sign = _SLIPPAGE_SIGN.get((direction, side), 0)
    if sign == 0:
        return price
    return price * (1.0 + sign * slippage_pct)


def _commission(gross: float, commission_pct: float) -> float:
    """Compute per-side commission for a fill of given gross value."""
    if commission_pct <= 0:
        return 0.0
    return abs(gross) * commission_pct
