"""PositionExecutor — entry, exit, stop/target, cost, and margin logic.

Facade that delegates to PositionSizer, PositionOpener, PositionCloser,
and IntrabarExitResolver. The bar loop calls the four public methods;
internal mechanics are composed from smaller, independently testable units.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from finbar_strategy_runtime.simulation.execution_config import ExecutionConfig
from finbar_strategy_runtime.simulation.intrabar_exit_resolver import (
    IntrabarExitResolver,
)
from finbar_strategy_runtime.simulation.margin_account_manager import (
    MarginAccountManager,
)
from finbar_strategy_runtime.simulation.pending_entry import PendingEntry
from finbar_strategy_runtime.simulation.position_closer import (
    PositionCloser,
)
from finbar_strategy_runtime.simulation.position_closer import (
    _apply_slippage as _apply_slippage_shared,
)
from finbar_strategy_runtime.simulation.position_closer import (
    _commission as _commission_shared,
)
from finbar_strategy_runtime.simulation.position_opener import PositionOpener
from finbar_strategy_runtime.simulation.position_sizer import PositionSizer
from finbar_strategy_runtime.simulation.simulation_state import SimulationState

logger = logging.getLogger(__name__)

# Multiplicative sign per (direction, side): entry longens and exit shortens
# for longs; the reverse for shorts. Kept for backward compatibility; the
# canonical sign table now lives in ``position_closer`` (single source).
_SLIPPAGE_SIGN: dict[tuple[str, str], float] = {
    ("long", "entry"): 1.0,
    ("long", "exit"): -1.0,
    ("short", "entry"): -1.0,
    ("short", "exit"): 1.0,
}


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
            self._opener.bind_margin_manager(self._margin)

    def sync_margin_equity(self, state: SimulationState) -> None:
        """Sync SimulationState.cash to margin account equity.

        No-op in simplified mode.
        """
        if self._full_margin and self._margin:
            self._margin.sync_state_equity(state)

    def apply_funding(self, state: SimulationState) -> None:
        """Apply per-bar funding payment to open position.

        No-op when funding is disabled or in simplified mode. The signed
        payment is accumulated on ``state.total_funding`` so the result
        reconciliation can account for it, and ``state.cash`` is re-synced
        from the margin account immediately so the equity curve recorded
        for this bar reflects the funding payment.
        """
        if self._full_margin and self._margin:
            payment = self._margin.apply_funding(state.position)
            if payment != 0.0:
                state.total_funding += payment
            self._margin.sync_state_equity(state)

    def check_margin_call(self, state: SimulationState, close: float) -> None:
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
        state: SimulationState,
        entry: PendingEntry,
        price: float,
        date: str,
    ) -> None:
        """Enter a new position from a pending entry signal."""
        fill_price = self._apply_slippage(price, entry.direction, "entry")
        entry = self._rebase_risk_prices(entry, fill_price)
        if not self._opener.stop_valid(entry, fill_price, date):
            return
        portfolio = self._portfolio_value(state, fill_price)
        size = self._sizer.resolve(state, entry, fill_price, portfolio, date)
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
        state: SimulationState,
        exit_price: float,
        bar_date: str,
        exit_reason: str = "signal",
    ) -> None:
        """Close the current position and record the trade.

        Thin Facade over :meth:`PositionCloser.close`, which owns the full
        exit settlement (slippage, PnL, margin, borrow, trade recording).
        """
        self._closer.close(
            state,
            exit_price,
            bar_date,
            exit_reason,
            slippage_pct=self._slippage_pct,
            commission_pct=self._commission_pct,
            margin_manager=self._margin,
        )

    def check_exit_conditions(
        self,
        state: SimulationState,
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
        state: SimulationState,
        final_close: float,
        final_date: str,
    ) -> None:
        """Close any open position at the final bar close."""
        if state.position.size == 0:
            return
        self.exit_position(
            state, final_close, final_date, exit_reason="end_of_backtest"
        )
        if state.equity_curve:
            last = state.equity_curve[-1]
            portfolio_val = self._portfolio_value(state, final_close)
            if portfolio_val > state.peak_value:
                state.peak_value = portfolio_val
            dd = (
                (state.peak_value - portfolio_val) / state.peak_value
                if state.peak_value > 0
                else 0.0
            )
            # Replace the last entry rather than mutating it in-place so
            # no stale references survive.
            state.equity_curve[-1] = {
                **last,
                "value": portfolio_val,
                "position": 0,
                "drawdown": dd,
            }

    @staticmethod
    def portfolio_value(state: SimulationState, close: float) -> float:
        return PositionExecutor._portfolio_value(state, close)

    # -- Private: callbacks and helpers ---------------------------------

    def _on_liquidated(
        self,
        state: SimulationState,
        price: float,
        date: str,
        reason: str,
    ) -> None:
        """Callback invoked by the closer when liquidation is triggered."""
        self.exit_position(state, price, date, exit_reason=reason)

    @staticmethod
    def _portfolio_value(state: SimulationState, close: float) -> float:
        """Calculate current portfolio value."""
        if state.position.size > 0:
            return state.cash + state.position.size * close
        if state.position.size < 0:
            return state.cash - abs(state.position.size) * close
        return state.cash

    def _rebase_risk_prices(
        self, entry: PendingEntry, fill_price: float
    ) -> PendingEntry:
        """Rebase stop/target from signal close to entry fill when configured.

        When ``risk_price_basis == "entry_fill"``, stop and target levels are
        proportionally scaled so the risk distance moves with the fill price.
        This keeps the risk/reward ratio consistent regardless of gaps between
        the signal bar close and the entry fill.

        Returns the original entry unchanged for ``signal_close`` mode or when
        the signal close is not available.
        """
        if self._config.risk_price_basis != "entry_fill":
            return entry
        if entry.signal_close <= 0:
            return entry
        ratio = fill_price / entry.signal_close
        return replace(
            entry,
            stop_price=_scale_price(
                entry.stop_price, entry.signal_close, fill_price, ratio
            ),
            target_price=_scale_price(
                entry.target_price, entry.signal_close, fill_price, ratio
            ),
        )

    def _apply_slippage(self, price: float, direction: str, side: str) -> float:
        """Apply directional slippage (delegates to the shared helper)."""
        return _apply_slippage_shared(
            price, direction, side, self._slippage_pct
        )

    def _commission(self, gross: float) -> float:
        """Per-side commission (delegates to the shared helper)."""
        return _commission_shared(gross, self._commission_pct)


def _scale_price(
    old_price: float,
    signal_close: float,
    fill_price: float,
    ratio: float,
) -> float:
    """Scale a risk price from signal close to entry fill.

    Uses proportional rebasing: the distance from the signal close is
    scaled by ``fill_price / signal_close``. Returns the original price
    unchanged when it is zero (disabled).
    """
    if old_price <= 0:
        return old_price
    return fill_price + (old_price - signal_close) * ratio
