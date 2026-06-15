"""MarginAccountManager — manages full margin accounting for one backtest.

Only used when ExecutionConfig.margin_mode == "full". In simplified mode,
all accounting is done through BacktestLoopState.cash directly.
"""

from __future__ import annotations

from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.margin_account import MarginAccount
from finbar.infrastructure.services.backtest_loop_state import BacktestLoopState
from finbar.infrastructure.services.backtest_position import BacktestPosition


class MarginAccountManager:
    """Full margin accounting: separate cash/margin, funding, margin calls.

    Delegates to BacktestLoopState for trade recording and position storage;
    owns MarginAccount for balance sheet separation.
    """

    def __init__(self, config: ExecutionConfig, initial_cash: float) -> None:
        """Create a manager for the full-margin accounting mode.

        Args:
            config: Execution configuration with margin settings.
            initial_cash: Starting capital transferred to margin_account.cash.
        """
        self._config = config
        self._maint_pct = config.maintenance_margin_pct
        self._funding_enabled = config.enable_funding
        self._funding_rate = config.funding_rate
        self.account = MarginAccount(cash=initial_cash)

    # -- Public API -----------------------------------------------------

    def lock_entry_margin(
        self, state: BacktestLoopState, cost: float, commission: float
    ) -> None:
        """Mirror a long entry and track its locked margin.

        ``PositionOpener`` has already applied the entry cash flow to
        ``state.cash`` before calling this method. The margin account must
        therefore mirror that state instead of applying the same cash flow a
        second time; otherwise a later exit releases/settles against an
        account balance that no longer matches the backtest state.
        """
        margin = (
            cost / self._config.leverage_multiplier
            if self._config.leverage_multiplier > 0
            else cost
        )
        self.account.margin_book += margin
        if state.cash == self.account.cash:
            self.account.cash -= cost + commission
        else:
            self.account.cash = state.cash

    def credit_entry_short(
        self, state: BacktestLoopState, cost: float, commission: float
    ) -> None:
        """Mirror or apply a short entry cash credit."""
        if state.cash == self.account.cash:
            self.account.cash += cost - commission
        else:
            self.account.cash = state.cash

    def settle_exit(
        self,
        state: BacktestLoopState,
        fill_cost: float,
        commission: float,
        abs_size: float,
        entry_price: float,
        direction: str,
        borrow_cost: float,
    ) -> None:
        """Settle cash after exit: reverse margin, return proceeds.

        Long:  cash += fill_cost - commission
        Short: cash -= fill_cost + commission + borrow_cost
        Also releases margin.
        """
        entry_notional = abs_size * entry_price
        margin_locked = (
            entry_notional / self._config.leverage_multiplier
            if self._config.leverage_multiplier > 0
            else entry_notional
        )
        self.account.release_margin(min(margin_locked, self.account.margin_book))
        # ``PositionExecutor`` has already applied the exit settlement to
        # ``state.cash``. Mirror that authoritative value after releasing the
        # margin book so mid-backtest exits do not double-count principal.
        self.account.cash = state.cash

    def sync_state_equity(self, state: BacktestLoopState) -> None:
        """Sync BacktestLoopState.cash to margin account equity."""
        state.cash = self.account.equity

    def apply_funding(self, position: BacktestPosition) -> float:
        """Apply one bar's funding payment to the open position.

        Only applies when enable_funding is True and position is open.

        Returns:
            The signed funding payment applied to cash (positive = paid by
            the position holder, negative = received). Zero when no payment
            is applied.
        """
        if not self._funding_enabled or position.size == 0:
            return 0.0
        abs_size = abs(position.size)
        if abs_size <= 0 or position.entry_price <= 0:
            return 0.0
        notional = abs_size * position.entry_price
        payment = notional * self._funding_rate
        if position.size < 0:
            payment = -payment  # shorts receive funding
        self.account.apply_funding(payment)
        return payment

    def check_margin_call(self, position: BacktestPosition, close: float) -> str | None:
        """Check if position is in margin-call territory.

        Returns "liquidation" when price crosses liquidation boundary.
        Returns None when safe.
        """
        if position.size == 0 or self._config.leverage_multiplier <= 1:
            return None
        abs_size = abs(position.size)
        entry_price = position.entry_price
        if entry_price <= 0 or abs_size <= 0:
            return None
        if position.liquidation_price > 0:
            if position.size > 0 and close <= position.liquidation_price:
                return "liquidation"
            if position.size < 0 and close >= position.liquidation_price:
                return "liquidation"
        return None
