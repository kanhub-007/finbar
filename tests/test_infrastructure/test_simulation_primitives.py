"""Tests for Slice 2 primitives in the simulation subpackage.

Scenario S6: Finbar's backtest is unchanged after primitives move to package.
Scenario S7: Fill primitives are independently composable.
"""

import pytest

from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.infrastructure.services.backtest_runner import BacktestRunner


def _simple_ohlcv_df(n: int = 50) -> "pd.DataFrame":
    """Create a simple OHLCV DataFrame with a gentle uptrend."""
    import numpy as np
    import pandas as pd

    dates = pd.date_range("2024-01-01", periods=n, freq="h")
    rng = np.random.RandomState(42)
    close = 100 + np.cumsum(rng.randn(n) * 0.5)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1000,
        },
        index=dates,
    )


class TestBacktestParityAfterMove:
    """Scenario S6: Backtest unchanged after primitives moved to package."""

    def test_backtest_produces_valid_result(self):
        """BacktestRunner.run() produces a valid result with trades."""
        import copy

        from finbar_strategy_runtime.domain.entities.signal_result import (
            SignalResult,
        )

        df = _simple_ohlcv_df(30)

        class SimpleStrategy:
            entered = False

            def on_reset(self):
                pass

            def meta(self):
                class Meta:
                    name = "test"
                return Meta()

            def on_bar(self, bar, position=None):
                close = float(bar["close"])
                if not self.entered:
                    self.entered = True
                    return SignalResult(direction="long", stop_price=close * 0.95)
                return SignalResult(direction="hold")

        runner = BacktestRunner()
        result = runner.run(
            df=df,
            strategy=SimpleStrategy(),
            initial_cash=10_000.0,
            risk_per_trade=0.10,
        )

        assert "trades" in result
        assert result["initial_cash"] == 10_000.0


class TestFillPrimitivesComposable:
    """Scenario S7: Fill primitives are independently composable."""

    def test_position_executor_enter_and_exit(self):
        """PositionExecutor can enter a position, check exits, and close it."""
        from finbar_strategy_runtime.simulation.execution_config import (
            ExecutionConfig,
        )
        from finbar_strategy_runtime.simulation.pending_entry import PendingEntry
        from finbar_strategy_runtime.simulation.position_executor import (
            PositionExecutor,
        )
        from finbar_strategy_runtime.simulation.simulation_state import (
            SimulationState,
        )

        # Spot with no buying-power cap to test raw formula
        config = ExecutionConfig(
            leverage_multiplier=1.0,
            risk_mode="leverage_scaled_risk",
            allow_negative_cash=True,
        )
        state = SimulationState(10_000.0)
        executor = PositionExecutor(config)

        entry = PendingEntry(
            direction="long",
            stop_price=92.0,
            risk_per_trade=0.10,
        )
        executor.enter(state, entry, price=100.0, date="2024-01-01T00:00:00")

        assert state.position.size > 0
        # Formula: equity * risk * leverage_budget / |entry - stop|
        # leverage_scaled_risk: multiplier = max(1, 1) = 1
        expected = (10_000.0 * 0.10 * 1.0) / abs(100.0 - 92.0)
        assert abs(state.position.size - expected) < 1e-6

        # Check exit conditions on a bar that breaches the stop
        executor.check_exit_conditions(
            state,
            open_price=99.0,
            high=99.5,
            low=90.0,
            bar_date="2024-01-01T01:00:00",
        )

        assert len(state.trades) >= 1
        trade = state.trades[-1]
        assert "exit_reason" in trade or "metadata" in trade

    def test_position_sizer_formula(self):
        """PositionSizer uses the formula: equity*risk*lev / |entry-stop|."""
        from finbar_strategy_runtime.simulation.execution_config import (
            ExecutionConfig,
        )
        from finbar_strategy_runtime.simulation.pending_entry import PendingEntry
        from finbar_strategy_runtime.simulation.position_sizer import PositionSizer
        from finbar_strategy_runtime.simulation.simulation_state import (
            SimulationState,
        )

        config = ExecutionConfig(
            leverage_multiplier=1.0,
            risk_mode="leverage_scaled_risk",
            allow_negative_cash=True,
        )
        sizer = PositionSizer(config)
        state = SimulationState(10_000.0)
        entry = PendingEntry(
            direction="long", stop_price=92.0, risk_per_trade=0.10
        )

        size = sizer.resolve(state, entry, entry_price=100.0, portfolio_value=10_000.0)

        expected = (10_000.0 * 0.10 * 1.0) / abs(100.0 - 92.0)
        assert abs(size - expected) < 1e-6
        assert size > 0

    def test_simulation_state_tracks_cash_and_trades(self):
        """SimulationState tracks cash, trades, and equity curve."""
        from finbar_strategy_runtime.simulation.simulation_state import (
            SimulationState,
        )

        state = SimulationState(10_000.0)
        assert state.cash == 10_000.0
        assert state.trades == []
        assert state.equity_curve == []

    def test_liquidate_open_closes_position(self):
        """liquidate_open closes any remaining position at end-of-run."""
        from finbar_strategy_runtime.simulation.execution_config import (
            ExecutionConfig,
        )
        from finbar_strategy_runtime.simulation.pending_entry import PendingEntry
        from finbar_strategy_runtime.simulation.position_executor import (
            PositionExecutor,
        )
        from finbar_strategy_runtime.simulation.simulation_state import (
            SimulationState,
        )

        config = ExecutionConfig(
            leverage_multiplier=1.0,
            risk_mode="leverage_scaled_risk",
        )
        state = SimulationState(10_000.0)
        executor = PositionExecutor(config)

        entry = PendingEntry(
            direction="long", stop_price=92.0, risk_per_trade=0.10
        )
        executor.enter(state, entry, price=100.0, date="2024-01-01T00:00:00")
        assert state.position.size > 0

        executor.liquidate_open(state, final_close=100.0, final_date="2024-01-02T00:00:00")
        assert state.position.size == 0
        assert len(state.trades) >= 1
