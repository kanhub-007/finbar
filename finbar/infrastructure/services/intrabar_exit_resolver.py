"""IntrabarExitResolver — gap-aware stop, target, and liquidation resolution."""

from __future__ import annotations

from finbar.infrastructure.services.backtest_position import BacktestPosition


class IntrabarExitResolver:
    """Resolve intrabar stop-loss, take-profit, and liquidation exits.

    Pure logic with no cost, cash, or portfolio dependencies — can be
    tested in isolation from the main executor.
    """

    @staticmethod
    def resolve(
        position: BacktestPosition,
        open_price: float,
        high: float,
        low: float,
    ) -> tuple[float, str] | None:
        """Return (exit_price, reason) or None when no exit is triggered."""
        stop = position.stop_price
        target = position.target_price
        if position.size > 0:
            return IntrabarExitResolver._resolve_long(
                open_price, high, low, stop, target
            )
        if position.size < 0:
            return IntrabarExitResolver._resolve_short(
                open_price, high, low, stop, target
            )
        return None

    @staticmethod
    def _resolve_long(
        open_price: float,
        high: float,
        low: float,
        stop: float,
        target: float,
    ) -> tuple[float, str] | None:
        """Gap-aware stop/target for long positions.

        Checks gap conditions first (open already beyond the level), then
        intrabar price action. Stop-loss takes priority over take-profit
        when both are touched in the same bar.
        """
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
    def _resolve_short(
        open_price: float,
        high: float,
        low: float,
        stop: float,
        target: float,
    ) -> tuple[float, str] | None:
        """Gap-aware stop/target for short positions."""
        if stop > 0 and open_price >= stop:
            return open_price, "stop_loss_gap"
        if target > 0 and open_price <= target:
            return open_price, "take_profit_gap"
        if stop > 0 and high >= stop:
            return stop, "stop_loss"
        if target > 0 and low <= target:
            return target, "take_profit"
        return None
