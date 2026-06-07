"""Unit tests for PositionSizer — pure sizing/affordability logic."""

from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.pending_entry import PendingEntry
from finbar.infrastructure.services.backtest_loop_state import BacktestLoopState
from finbar.infrastructure.services.position_sizer import PositionSizer


class TestRawSizing:
    def test_explicit_size_returns_given_size_when_allowed(self):
        config = ExecutionConfig(allow_negative_cash=True)
        sizer = PositionSizer(config)
        entry = PendingEntry(
            direction="long",
            position_size=500,
            explicit_size=True,
            stop_price=95.0,
            risk_per_trade=0.02,
        )

        size = sizer.resolve(
            BacktestLoopState(10000), entry, 100.0, portfolio_value=10000.0
        )

        assert size == 500

    def test_explicit_size_capped_by_default(self):
        """Default config caps explicit size to affordability."""
        sizer = PositionSizer(ExecutionConfig())
        entry = PendingEntry(
            direction="long",
            position_size=500,
            explicit_size=True,
            stop_price=95.0,
            risk_per_trade=0.02,
        )

        size = sizer.resolve(
            BacktestLoopState(10000), entry, 100.0, portfolio_value=10000.0
        )

        assert size == 100  # capped by max_affordable = 10000 / 100

    def test_risk_based_with_stop_computes_correctly(self):
        sizer = PositionSizer(ExecutionConfig())
        entry = PendingEntry(
            direction="long",
            stop_price=95.0,
            risk_per_trade=0.02,
        )

        size = sizer.resolve(
            BacktestLoopState(10000), entry, 100.0, portfolio_value=10000.0
        )
        # risk_amount = 10000 * 0.02 = 200, risk_per_share = 5, size = 40
        assert size == 40

    def test_risk_based_no_stop_falls_back_to_default(self):
        sizer = PositionSizer(ExecutionConfig())
        entry = PendingEntry(
            direction="long",
            stop_price=0.0,
            risk_per_trade=0.02,
        )

        size = sizer.resolve(
            BacktestLoopState(10000), entry, 100.0, portfolio_value=10000.0
        )

        assert size == 100.0

    def test_leverage_scaled_risk_multiplies_budget(self):
        config = ExecutionConfig(
            risk_mode="leverage_scaled_risk", leverage_multiplier=3.0
        )
        sizer = PositionSizer(config)
        entry = PendingEntry(
            direction="long",
            stop_price=90.0,
            risk_per_trade=0.02,
        )

        size = sizer.resolve(
            BacktestLoopState(10000), entry, 100.0, portfolio_value=10000.0
        )
        # risk_amount = 10000 * 0.02 * 3 = 600, risk_per_share = 10, size = 60
        assert size == 60

    def test_size_clamped_at_zero_for_tiny_risk_per_share(self):
        sizer = PositionSizer(ExecutionConfig())
        entry = PendingEntry(
            direction="long",
            stop_price=100.0,  # no risk distance
            risk_per_trade=0.02,
        )

        size = sizer.resolve(
            BacktestLoopState(10000), entry, 100.0, portfolio_value=10000.0
        )
        # risk_per_share < 0.001 so falls back to default
        assert size == 100.0


class TestAffordabilityCap:
    def test_cap_limits_size_to_buying_power(self):
        sizer = PositionSizer(ExecutionConfig())
        entry = PendingEntry(
            direction="long",
            position_size=500,
            explicit_size=True,
            stop_price=95.0,
            risk_per_trade=0.02,
        )

        size = sizer.resolve(
            BacktestLoopState(10000),
            entry,
            100.0,
            portfolio_value=10000.0,
        )
        # max_affordable = 10000 / 100 = 100, so 500 → 100
        assert size == 100

    def test_no_cap_when_allow_negative_cash(self):
        config = ExecutionConfig(allow_negative_cash=True)
        sizer = PositionSizer(config)
        entry = PendingEntry(
            direction="long",
            position_size=500,
            explicit_size=True,
            stop_price=95.0,
            risk_per_trade=0.02,
        )

        size = sizer.resolve(
            BacktestLoopState(5000),
            entry,
            100.0,
            portfolio_value=5000.0,
        )

        assert size == 500

    def test_cap_uses_effective_price_including_commission(self):
        config = ExecutionConfig(commission_pct=0.01)
        sizer = PositionSizer(config)
        entry = PendingEntry(
            direction="long",
            position_size=500,
            explicit_size=True,
            stop_price=95.0,
            risk_per_trade=0.02,
        )

        size = sizer.resolve(
            BacktestLoopState(10000),
            entry,
            100.0,
            portfolio_value=10000.0,
        )
        # effective_price = 100 * 1.01 = 101, max = 10000 / 101 ≈ 99
        assert size < 500
        assert size <= 99.01

    def test_zero_cash_produces_zero_size(self):
        sizer = PositionSizer(ExecutionConfig())
        entry = PendingEntry(
            direction="long",
            position_size=100,
            explicit_size=True,
            stop_price=95.0,
            risk_per_trade=0.02,
        )

        state = BacktestLoopState(0)
        size = sizer.resolve(state, entry, 100.0, portfolio_value=0.0)

        assert size == 0.0
        assert len(state.diagnostics) > 0
        assert state.diagnostics[0].code == "insufficient_cash"


class TestExplicitSizePolicy:
    def test_reject_policy_returns_zero_for_oversized(self):
        config = ExecutionConfig(reject_oversized_explicit_orders=True)
        sizer = PositionSizer(config)
        entry = PendingEntry(
            direction="long",
            position_size=500,
            explicit_size=True,
            stop_price=95.0,
            risk_per_trade=0.02,
        )

        state = BacktestLoopState(10000)
        size = sizer.resolve(state, entry, 100.0, portfolio_value=10000.0)

        assert size == 0.0
        assert any(d.code == "explicit_size_rejected" for d in state.diagnostics)

    def test_cap_explicit_disabled_rejects_oversized(self):
        """cap_explicit_size=False means reject rather than cap."""
        config = ExecutionConfig(cap_explicit_size=False)
        sizer = PositionSizer(config)
        entry = PendingEntry(
            direction="long",
            position_size=500,
            explicit_size=True,
            stop_price=95.0,
            risk_per_trade=0.02,
        )

        state = BacktestLoopState(10000)
        size = sizer.resolve(state, entry, 100.0, portfolio_value=10000.0)

        assert size == 0.0
        assert any(d.code == "explicit_size_rejected" for d in state.diagnostics)
