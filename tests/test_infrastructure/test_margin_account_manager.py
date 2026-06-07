"""Tests for MarginAccount and MarginAccountManager."""

import pytest

from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.margin_account import MarginAccount
from finbar.infrastructure.services.backtest_position import BacktestPosition
from finbar.infrastructure.services.margin_account_manager import (
    MarginAccountManager,
)


class TestMarginAccount:
    def test_initial_state(self):
        acct = MarginAccount(cash=10000)
        assert acct.cash == 10000
        assert acct.margin_book == 0
        assert acct.equity == 10000

    def test_lock_margin(self):
        acct = MarginAccount(cash=10000)
        acct.lock_margin(3000)
        assert acct.cash == 7000
        assert acct.margin_book == 3000
        assert acct.equity == 7000

    def test_lock_margin_limited_by_cash(self):
        acct = MarginAccount(cash=500)
        acct.lock_margin(1000)
        assert acct.cash == 0
        assert acct.margin_book == 500

    def test_release_margin(self):
        acct = MarginAccount(cash=7000, margin_book=3000)
        acct.release_margin(1000)
        assert acct.cash == 8000
        assert acct.margin_book == 2000

    def test_release_margin_limited_by_book(self):
        acct = MarginAccount(cash=7000, margin_book=1000)
        acct.release_margin(2000)
        assert acct.cash == 8000
        assert acct.margin_book == 0

    def test_unrealized_pnl_does_not_affect_equity(self):
        """Equity = cash only; position value tracked by bar loop."""
        acct = MarginAccount(cash=5000, margin_book=2000, unrealized_pnl=500)
        assert acct.equity == 5000

    def test_negative_unrealized_does_not_affect_equity(self):
        acct = MarginAccount(cash=5000, margin_book=3000, unrealized_pnl=-500)
        assert acct.equity == 5000

    def test_available_margin(self):
        acct = MarginAccount(cash=5000, margin_book=2000)
        assert acct.available_margin == 3000  # cash - margin_book

    def test_apply_funding(self):
        acct = MarginAccount(cash=10000)
        acct.apply_funding(10)
        assert acct.cash == 9990
        assert acct.total_funding_paid == 10

    def test_apply_borrow(self):
        acct = MarginAccount(cash=10000)
        acct.apply_borrow(5)
        assert acct.cash == 9995
        assert acct.total_borrow_cost == 5


class TestMarginAccountManager:
    def _config(self, **kwargs):
        return ExecutionConfig(
            leverage_multiplier=kwargs.get("leverage_multiplier", 3.0),
            margin_mode="full",
            maintenance_margin_pct=kwargs.get("maintenance_margin_pct", 0.005),
            enable_funding=kwargs.get("enable_funding", False),
            funding_rate=kwargs.get("funding_rate", 0.0001),
        )

    def test_initialization(self):
        config = self._config()
        mgr = MarginAccountManager(config, 10000)
        assert mgr.account.cash == 10000
        assert mgr.account.equity == 10000

    def test_lock_entry_margin_long(self):
        from finbar.infrastructure.services.backtest_loop_state import (
            BacktestLoopState,
        )

        mgr = MarginAccountManager(self._config(), 10000)
        state = BacktestLoopState(10000)
        mgr.lock_entry_margin(state, cost=3000, commission=10)
        assert mgr.account.cash == 6990
        assert mgr.account.margin_book == pytest.approx(1000)  # 3000/3

    def test_credit_entry_short(self):
        from finbar.infrastructure.services.backtest_loop_state import (
            BacktestLoopState,
        )

        mgr = MarginAccountManager(self._config(), 10000)
        state = BacktestLoopState(10000)
        mgr.credit_entry_short(state, cost=3000, commission=10)
        assert mgr.account.cash == 12990  # 10000 + 3000 - 10

    def test_sync_state_equity(self):
        from finbar.infrastructure.services.backtest_loop_state import (
            BacktestLoopState,
        )

        mgr = MarginAccountManager(self._config(), 10000)
        state = BacktestLoopState(0)
        mgr.account.cash = 9500
        mgr.account.margin_book = 1000
        mgr.account.unrealized_pnl = -200
        mgr.sync_state_equity(state)
        assert state.cash == 9500

    def test_funding_disabled_noop(self):
        mgr = MarginAccountManager(self._config(enable_funding=False), 10000)
        pos = BacktestPosition()
        pos.size = 100
        pos.entry_price = 100
        pos.direction = "long"
        mgr.apply_funding(pos)
        assert mgr.account.total_funding_paid == 0

    def test_funding_long_pays(self):
        mgr = MarginAccountManager(self._config(enable_funding=True), 10000)
        pos = BacktestPosition()
        pos.size = 100
        pos.entry_price = 100
        pos.direction = "long"
        mgr.apply_funding(pos)
        assert mgr.account.total_funding_paid > 0
        assert mgr.account.cash < 10000

    def test_margin_call_safe(self):
        mgr = MarginAccountManager(self._config(), 10000)
        pos = BacktestPosition()
        pos.size = 10
        pos.entry_price = 100
        pos.direction = "long"
        pos.liquidation_price = 33.33
        result = mgr.check_margin_call(pos, close=100)
        assert result is None

    def test_margin_call_liquidation_long(self):
        mgr = MarginAccountManager(self._config(), 10000)
        pos = BacktestPosition()
        pos.size = 10
        pos.entry_price = 100
        pos.direction = "long"
        pos.liquidation_price = 70
        result = mgr.check_margin_call(pos, close=69)
        assert result == "liquidation"

    def test_margin_call_liquidation_short(self):
        mgr = MarginAccountManager(self._config(), 10000)
        pos = BacktestPosition()
        pos.size = -10
        pos.entry_price = 100
        pos.direction = "short"
        pos.liquidation_price = 130
        result = mgr.check_margin_call(pos, close=131)
        assert result == "liquidation"

    def test_simplified_mode_noop(self):
        """Simplified mode doesn't create margin manager."""
        config = ExecutionConfig(margin_mode="simplified")
        mgr = MarginAccountManager(config, 10000)
        # In practice this wouldn't be constructed; verify it doesn't crash
        assert mgr.account.cash == 10000
