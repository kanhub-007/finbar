"""Spec 2026-06-23 Scenario 2 — backtests reject bars without timestamps.

Bars without a parseable ``timestamp`` must never be silently accepted,
because the backtest engine derives ``start_date``/``end_date`` and
calendar analytics from the DataFrame index. Without a timestamp the
index would fall back to row numbers, producing fake dates and corrupting
monthly/yearly/annualization metrics.

Classical school, black-box: real converters and real use cases with a
stub engine/strategy. We assert on the returned ``BacktestResultDTO`` /
``BacktestStrategyDefinitionResult`` outcome, never on private helpers.
"""

from __future__ import annotations

from finbar.core.application.dto.backtest_request import BacktestRequest
from finbar.core.application.dto.backtest_result import BacktestResultDTO
from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
)
from finbar.core.application.use_cases.run_backtest import RunBacktestUseCase
from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)

_OHLCV_NO_TS = {
    "open": 100,
    "high": 105,
    "low": 98,
    "close": 102,
    "volume": 1_000_000,
}


class _NeverTradingStrategy(TradingStrategy):
    """A strategy that never trades; sufficient to drive the use case."""

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="never",
            variant=DataMode.REAL,
            description="Never trades",
            required_indicators=[],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        return SignalResult(action="hold")


class _RecordingProvider:
    """Strategy provider returning a never-trading strategy for any name."""

    def __init__(self):
        self.params_seen = None

    def create(self, name: str, params: dict | None = None):
        self.params_seen = params
        return _NeverTradingStrategy()

    def list_metadata(self):
        return [_NeverTradingStrategy().meta()]

    def exists(self, name: str) -> bool:
        return True

    def definition_for(self, name: str):  # noqa: ARG002
        return None


class _StubEngine:
    """Engine returning a fixed success dict — should not be reached on bad input."""

    def __init__(self):
        self.reached = False

    def run(self, df, strategy, initial_cash: float = 10000.0, **params):  # noqa: ARG002
        self.reached = True
        return {
            "strategy_name": strategy.meta().name,
            "start_date": "should-not-reach",
            "end_date": "should-not-reach",
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
            "annualization_factor": 252.0,
            "annualization_warning": "",
        }


def _bars_without_timestamp(count: int = 2) -> list[dict]:
    return [dict(_OHLCV_NO_TS) for _ in range(count)]


class TestRunBacktestRejectsBarsWithoutTimestamp:
    """RunBacktestUseCase (named-strategy path) validation."""

    def _use_case(self) -> tuple[RunBacktestUseCase, _StubEngine]:
        engine = _StubEngine()
        use_case = RunBacktestUseCase(
            engine,
            _RecordingProvider(),
            PandasBarFrameConverter(),
        )
        return use_case, engine

    def test_raw_bars_without_timestamp_return_error(self):
        use_case, engine = self._use_case()
        result = use_case.execute(
            BacktestRequest(
                bars=_bars_without_timestamp(),
                strategy_name="never",
            )
        )

        assert isinstance(result, BacktestResultDTO)
        assert result.error is not None
        assert "timestamp" in result.error.lower()
        assert result.start_date == ""
        assert not engine.reached, "engine must not run on timestamp-less bars"

    def test_enriched_bars_without_timestamp_return_error(self):
        """Pre-enriched bars must also carry a timestamp."""
        use_case, engine = self._use_case()
        bars = _bars_without_timestamp()
        bars[0]["sma_20"] = 99.0  # marks bars as pre-enriched
        bars[1]["sma_20"] = 99.5

        result = use_case.execute(
            BacktestRequest(bars=bars, strategy_name="never")
        )

        assert result.error is not None
        assert "timestamp" in result.error.lower()
        assert not engine.reached

    def test_timestamped_bars_still_run(self):
        """Regression guard: bars with timestamps are accepted."""
        use_case, engine = self._use_case()
        bars = [
            {
                "timestamp": "2024-01-01",
                **_OHLCV_NO_TS,
            },
            {
                "timestamp": "2024-01-02",
                **_OHLCV_NO_TS,
                "close": 103,
            },
        ]
        result = use_case.execute(
            BacktestRequest(bars=bars, strategy_name="never")
        )

        assert result.error is None
        assert engine.reached

    def test_empty_bars_still_give_no_bars_error(self):
        """The existing 'No bars provided' path must remain unchanged."""
        use_case, engine = self._use_case()
        result = use_case.execute(
            BacktestRequest(bars=[], strategy_name="never")
        )

        assert result.error is not None
        assert "timestamp" not in result.error.lower()


class TestBacktestStrategyDefinitionRejectsBarsWithoutTimestamp:
    """The unsaved JSON-definition backtest path validation."""

    def test_raw_bars_without_timestamp_return_error(self):
        from finbar.core.application.use_cases.backtest_strategy_definition import (
            BacktestStrategyDefinitionUseCase,
        )

        engine = _StubEngine()
        use_case = BacktestStrategyDefinitionUseCase(
            engine=engine,
            converter=PandasBarFrameConverter(),
            strategy_factory=None,  # type: ignore[arg-type]
            parser=None,  # type: ignore[arg-type]
        )

        definition = {
            "schema_version": "2.0",
            "name": "no-ts",
            "timeframes": {"primary": "1d"},
            "indicators": [],
            "sides": {"long": {}, "short": {}},
            "conditions": {"entry": {"long": [], "short": []}},
        }
        result = use_case.execute(
            BacktestStrategyDefinitionRequest(
                definition=definition,
                bars=_bars_without_timestamp(),
                execution=ExecutionConfig(),
                symbol="TEST",
                interval="1d",
            )
        )

        assert result.valid is False
        messages = " ".join(err.message for err in result.errors)
        assert "timestamp" in messages.lower()
        assert not engine.reached
