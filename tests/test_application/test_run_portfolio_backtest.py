"""Integration tests for portfolio backtest use case."""

import pytest

from finbar.core.application.dto.portfolio_backtest_request import (
    PortfolioBacktestRequest,
)
from finbar.core.application.use_cases.run_portfolio_backtest import (
    RunPortfolioBacktestUseCase,
    _aggregate_equity,
    _compute_returns,
    _correlation_matrix,
)
from finbar.core.domain.entities.data_mode import DataMode
from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.portfolio_config import AssetAllocation
from finbar.core.domain.entities.portfolio_result import PortfolioResult
from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)


class _StubStrategy(TradingStrategy):
    """Strategy that never trades (no signals)."""

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="stub",
            variant=DataMode.REAL,
            description="Stub",
            required_indicators=["sma_5", "sma_10"],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        return SignalResult(action="hold")

    def on_reset(self) -> None:
        pass

    @property
    def warmup_bars(self):
        return 0


class _StubProvider:
    """Returns stub strategy for any name."""

    def create(self, name: str, params: dict | None = None):
        return _StubStrategy()


def _make_test_bars(count=100, close_fn=None):
    """Generate test OHLCV bars."""
    bars = []
    for i in range(count):
        close = close_fn(i) if close_fn else 100.0 + i * 0.1
        bars.append(
            {
                "timestamp": f"2024-01-{i+1:02d}" if i < 31 else f"2024-02-{i-30:02d}",
                "open": close - 0.5,
                "high": close + 0.5,
                "low": close - 1.0,
                "close": close,
                "volume": 1000000,
                "sma_5": close,
                "sma_10": close,
            }
        )
    return bars


class TestPortfolioBacktestUseCase:
    def _create_use_case(self):
        return RunPortfolioBacktestUseCase(
            strategy_provider=_StubProvider(),
            engine=BacktestRunner(),
            converter=PandasBarFrameConverter(),
        )

    def test_empty_assets_returns_error(self):
        uc = self._create_use_case()
        request = PortfolioBacktestRequest(assets=[])
        result = uc.execute(request)
        assert isinstance(result, PortfolioResult)
        assert "No assets" in result.error

    def test_single_asset_produces_result(self):
        uc = self._create_use_case()
        bars = _make_test_bars(30)
        request = PortfolioBacktestRequest(
            assets=[
                AssetAllocation(
                    symbol="TEST", strategy_name="stub", weight=1.0, bars=bars
                )
            ],
            initial_cash=10000,
            interval="1d",
            execution=ExecutionConfig(),
        )
        result = uc.execute(request)
        assert result.error == ""
        assert len(result.equity_curve) > 0
        assert "TEST" in result.per_asset_results
        assert result.correlation_matrix == [[1.0]]

    def test_two_assets_produces_correlation(self):
        uc = self._create_use_case()
        bars1 = _make_test_bars(30)
        bars2 = _make_test_bars(30, close_fn=lambda i: 200.0 + i * 0.1)
        request = PortfolioBacktestRequest(
            assets=[
                AssetAllocation(
                    symbol="A", strategy_name="stub", weight=1.0, bars=bars1
                ),
                AssetAllocation(
                    symbol="B", strategy_name="stub", weight=1.0, bars=bars2
                ),
            ],
            initial_cash=100000,
            interval="1d",
            execution=ExecutionConfig(),
        )
        result = uc.execute(request)
        assert result.error == ""
        assert len(result.equity_curve) > 0
        assert len(result.correlation_matrix) == 2
        assert len(result.correlation_matrix[0]) == 2

    def test_weight_proportional_allocation(self):
        """Heavier weight gets more of the initial capital."""
        uc = self._create_use_case()
        bars = _make_test_bars(20)
        request = PortfolioBacktestRequest(
            assets=[
                AssetAllocation(
                    symbol="X", strategy_name="stub", weight=2.0, bars=bars
                ),
                AssetAllocation(
                    symbol="Y", strategy_name="stub", weight=1.0, bars=bars
                ),
            ],
            initial_cash=30000,
            interval="1d",
            execution=ExecutionConfig(),
        )
        result = uc.execute(request)
        x_result = result.per_asset_results.get("X", {})
        y_result = result.per_asset_results.get("Y", {})
        assert x_result.get("initial_cash", 0) == 20000
        assert y_result.get("initial_cash", 0) == 10000

    def test_portfolio_equity_is_sum_of_individual(self):
        uc = self._create_use_case()
        bars1 = _make_test_bars(30)
        bars2 = _make_test_bars(30, close_fn=lambda i: 200.0 + i * 0.1)
        request = PortfolioBacktestRequest(
            assets=[
                AssetAllocation(
                    symbol="A", strategy_name="stub", weight=1.0, bars=bars1
                ),
                AssetAllocation(
                    symbol="B", strategy_name="stub", weight=1.0, bars=bars2
                ),
            ],
            initial_cash=20000,
            interval="1d",
            execution=ExecutionConfig(),
        )
        result = uc.execute(request)
        eq_a = result.per_asset_results["A"]["equity_curve"]
        eq_b = result.per_asset_results["B"]["equity_curve"]
        portfolio_eq = result.equity_curve

        for p_entry in portfolio_eq:
            date = p_entry["date"]
            a_val = sum(e["value"] for e in eq_a if e["date"] == date)
            b_val = sum(e["value"] for e in eq_b if e["date"] == date)
            assert abs(p_entry["value"] - (a_val + b_val)) < 0.1


class TestHelperFunctions:
    def test_returns_from_rising_equity(self):
        eq = [
            {"date": "D1", "value": 100},
            {"date": "D2", "value": 110},
            {"date": "D3", "value": 121},
        ]
        result = _compute_returns(eq)
        assert len(result) == 2
        assert result[0] == pytest.approx(0.1)
        assert result[1] == pytest.approx(0.1)

    def test_correlation_identical_series(self):
        r1 = [0.01, 0.02, -0.01, 0.03]
        r2 = [0.01, 0.02, -0.01, 0.03]
        m = _correlation_matrix([r1, r2])
        assert m[0][1] == pytest.approx(1.0)

    def test_correlation_one_series(self):
        r1 = [0.01, 0.02]
        m = _correlation_matrix([r1])
        assert m == [[1.0]]

    def test_aggregate_empty_returns_empty(self):
        eq, metrics = _aggregate_equity({}, 10000, "1d", "equity_regular_hours")
        assert eq == []
