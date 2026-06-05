"""Unit tests for RunBacktestUseCase with mocked engine and registry."""

from finbar.core.application.dto.backtest_request import BacktestRequest
from finbar.core.application.dto.backtest_result import BacktestResultDTO
from finbar.core.application.use_cases.run_backtest import RunBacktestUseCase
from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.strategy_provider import StrategyProvider
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)


class StubStrategy(TradingStrategy):
    """A strategy that never trades."""

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="stub",
            variant=DataMode.REAL,
            description="Stub",
            required_indicators=[],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        return SignalResult(action="hold")


class StubStrategyProvider(StrategyProvider):
    """Records params used to create strategies."""

    def __init__(self):
        self.params_seen = None

    def create(self, name: str, params: dict | None = None) -> TradingStrategy | None:
        self.params_seen = params
        return StubStrategy() if name == "stub" else None

    def list_metadata(self) -> list[StrategyMeta]:
        return [StubStrategy().meta()]

    def exists(self, name: str) -> bool:
        return name == "stub"


class StubEngine:
    """Returns a fixed result dict."""

    def run(
        self,
        df,
        strategy: TradingStrategy,
        initial_cash: float = 10000.0,
        **params,
    ) -> dict:
        return {
            "strategy_name": strategy.meta().name,
            "symbol": "",
            "interval": "",
            "start_date": "2024-01-01",
            "end_date": "2024-01-10",
            "bar_count": len(df),
            "initial_cash": initial_cash,
            "final_value": initial_cash,
            "total_return": 0.0,
            "annualized_return": 0.0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "profit_factor": 0.0,
            "calmar_ratio": 0.0,
            "trades": [],
            "equity_curve": [],
        }


class TestRunBacktestUseCase:
    def setup_method(self):
        self.engine = StubEngine()
        self.strategy = StubStrategy()
        self.registry = {"stub": self.strategy}
        self.converter = PandasBarFrameConverter()
        self.use_case = RunBacktestUseCase(
            self.engine,
            self.registry,
            self.converter,
        )

    def test_empty_bars_returns_error(self):
        result = self.use_case.execute(BacktestRequest(bars=[], strategy_name="stub"))
        assert isinstance(result, BacktestResultDTO)
        assert result.error is not None

    def test_unknown_strategy_returns_error(self):
        bars = [
            {
                "timestamp": "2024-01-01",
                "open": 100,
                "high": 105,
                "low": 98,
                "close": 102,
                "volume": 1000000,
            }
        ]
        result = self.use_case.execute(
            BacktestRequest(bars=bars, strategy_name="nonexistent")
        )
        assert result.error is not None
        assert "Unknown" in result.error
        assert "stub" in result.error  # lists available strategies

    def test_successful_run(self):
        bars = [
            {
                "timestamp": "2024-01-01",
                "open": 100,
                "high": 105,
                "low": 98,
                "close": 102,
                "volume": 1000000,
            }
        ]
        result = self.use_case.execute(
            BacktestRequest(
                bars=bars,
                strategy_name="stub",
                symbol="AAPL",
                interval="1d",
            )
        )
        assert result.error is None
        assert result.strategy_name == "stub"
        assert result.symbol == "AAPL"
        assert result.interval == "1d"
        assert result.bar_count == 1

    def test_strategy_params_forwarded_to_provider(self):
        provider = StubStrategyProvider()
        use_case = RunBacktestUseCase(
            StubEngine(),
            provider,
            PandasBarFrameConverter(),
        )
        bars = [
            {
                "timestamp": "2024-01-01",
                "open": 100,
                "high": 105,
                "low": 98,
                "close": 102,
                "volume": 1000000,
            }
        ]
        result = use_case.execute(
            BacktestRequest(
                bars=bars,
                strategy_name="stub",
                params={"fast_period": 5, "slow_period": 10},
            )
        )
        assert result.error is None
        assert provider.params_seen == {"fast_period": 5, "slow_period": 10}

    def test_symbol_interval_passthrough(self):
        bars = [
            {
                "timestamp": "2024-01-01",
                "open": 100,
                "high": 105,
                "low": 98,
                "close": 102,
                "volume": 1000000,
            }
        ]
        result = self.use_case.execute(
            BacktestRequest(
                bars=bars,
                strategy_name="stub",
                symbol="TSLA",
                interval="1h",
            )
        )
        assert result.symbol == "TSLA"
        assert result.interval == "1h"
