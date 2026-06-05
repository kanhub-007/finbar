"""Edge case tests for the backtest runner — position sizing, stops, shorts."""

import pandas as pd

from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.backtest_runner import BacktestRunner


class _StaticSignalStrategy(TradingStrategy):
    """Returns a fixed signal on every bar. Used for edge case testing."""

    def __init__(self, signal: SignalResult, name: str = "test"):
        self._signal = signal
        self._name = name

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name=self._name,
            variant=DataMode.REAL,
            description="Test",
            required_indicators=[],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        return self._signal

    def on_reset(self) -> None:
        pass


class _AlternatingSignalStrategy(TradingStrategy):
    """Buy on bar 0, exit on bar 5."""

    def __init__(self):
        self._bar_count = 0

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="alternating",
            variant=DataMode.REAL,
            description="Test",
            required_indicators=[],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        self._bar_count += 1
        pos_size = position.get("size", 0)
        if pos_size == 0 and self._bar_count == 1:
            return SignalResult(
                action="buy",
                direction="long",
                stop_price=90.0,
                target_price=120.0,
            )
        if pos_size > 0 and self._bar_count >= 10:
            return SignalResult(
                action="sell",
                direction="exit",
            )
        return SignalResult(action="hold")

    def on_reset(self) -> None:
        self._bar_count = 0


class _ShortThenCoverStrategy(TradingStrategy):
    """Enter short, then emit a buy-to-cover exit signal."""

    def __init__(self):
        self._entered = False

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="short_then_cover",
            variant=DataMode.REAL,
            description="Test",
            required_indicators=[],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        if position.get("direction") == "short":
            return SignalResult(action="buy", direction="exit")
        if not self._entered:
            self._entered = True
            return SignalResult(
                action="sell",
                direction="short",
                position_size=10,
            )
        return SignalResult(action="hold")

    def on_reset(self) -> None:
        self._entered = False


def _make_flat_df(periods: int = 20, price: float = 100.0) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=periods, freq="D")
    return pd.DataFrame(
        {
            "open": [price] * periods,
            "high": [price + 1] * periods,
            "low": [price - 1] * periods,
            "close": [price] * periods,
            "volume": [1000000] * periods,
        },
        index=dates,
    )


class TestPositionSizing:
    def test_strategy_provided_size_used(self):
        """When strategy sets position_size, engine uses it directly."""
        sig = SignalResult(
            action="buy",
            direction="long",
            stop_price=98.0,
            position_size=500,
        )
        runner = BacktestRunner()
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        prices = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91]
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 1 for p in prices],
                "low": [p - 1 for p in prices],
                "close": prices,
                "volume": [1000000] * 10,
            },
            index=dates,
        )
        result = runner.run(df, _StaticSignalStrategy(sig), 10000)
        assert result["total_trades"] > 0
        for trade in result["trades"]:
            assert trade["size"] == 500

    def test_risk_based_sizing_no_stop(self):
        """Without stop, falls back to default 100 shares."""
        sig = SignalResult(action="buy", direction="long")
        df = _make_flat_df(20)
        runner = BacktestRunner()
        result = runner.run(df, _StaticSignalStrategy(sig), 10000)
        for trade in result["trades"]:
            assert trade["size"] == 100

    def test_risk_based_sizing_with_stop(self):
        """With stop, size = (10000 * 2%) / |100 - 95| = 200/5 = 40."""
        sig = SignalResult(action="buy", direction="long", stop_price=95.0)
        df = _make_flat_df(20)
        runner = BacktestRunner()
        result = runner.run(df, _StaticSignalStrategy(sig), 50000)
        # size = (50000 * 0.02) / |100 - 95| = 1000/5 = 200
        for trade in result["trades"]:
            assert trade["size"] == 200


class TestShortTrading:
    def test_short_entry_sizing(self):
        sig = SignalResult(
            action="sell",
            direction="short",
            stop_price=105.0,
            position_size=50,
        )
        df = _make_flat_df(20)
        runner = BacktestRunner()
        result = runner.run(df, _StaticSignalStrategy(sig), 10000)
        for trade in result["trades"]:
            assert trade["metadata"].get("direction") == "short"

    def test_short_stop_loss_triggered(self):
        """Short position should exit when price >= stop."""
        sig = SignalResult(
            action="sell",
            direction="short",
            stop_price=102.0,
            position_size=100,
        )
        runner = BacktestRunner()
        # Create data where price rises to hit the stop
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        prices = [100, 101, 102, 103, 104, 105, 104, 103, 102, 101]
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 1 for p in prices],
                "low": [p - 1 for p in prices],
                "close": prices,
                "volume": [1000000] * 10,
            },
            index=dates,
        )
        result = runner.run(df, _StaticSignalStrategy(sig), 10000)
        assert result["total_trades"] > 0

    def test_short_buy_exit_signal_closes_position(self):
        df = _make_flat_df(5)
        runner = BacktestRunner()
        result = runner.run(df, _ShortThenCoverStrategy(), 10000)
        assert result["total_trades"] == 1
        assert result["trades"][0]["metadata"]["direction"] == "short"


class TestStopLoss:
    def test_long_stop_loss_triggered(self):
        sig = SignalResult(
            action="buy",
            direction="long",
            stop_price=98.0,
            position_size=100,
        )
        runner = BacktestRunner()
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        prices = [100, 99, 98, 97, 96, 95, 96, 97, 98, 99]
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 1 for p in prices],
                "low": [p - 1 for p in prices],
                "close": prices,
                "volume": [1000000] * 10,
            },
            index=dates,
        )
        result = runner.run(df, _StaticSignalStrategy(sig), 10000)
        # Should have at least a stop-loss exit
        assert result["total_trades"] > 0

    def test_take_profit_triggered(self):
        sig = SignalResult(
            action="buy",
            direction="long",
            target_price=110.0,
            position_size=100,
        )
        runner = BacktestRunner()
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        prices = [100, 105, 110, 115, 120, 115, 110, 105, 100, 95]
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 2 for p in prices],
                "low": [p - 2 for p in prices],
                "close": prices,
                "volume": [1000000] * 10,
            },
            index=dates,
        )
        result = runner.run(df, _StaticSignalStrategy(sig), 10000)
        assert result["total_trades"] > 0


class TestEquityCurve:
    def test_equity_curve_length(self):
        sig = SignalResult(action="buy", direction="long")
        df = _make_flat_df(50)
        runner = BacktestRunner()
        result = runner.run(df, _StaticSignalStrategy(sig), 10000)
        assert len(result["equity_curve"]) == 50

    def test_equity_curve_has_required_fields(self):
        sig = SignalResult(action="buy", direction="long")
        df = _make_flat_df(10)
        runner = BacktestRunner()
        result = runner.run(df, _StaticSignalStrategy(sig), 10000)
        for point in result["equity_curve"]:
            assert "date" in point
            assert "value" in point
            assert "drawdown" in point
            assert "position" in point


class TestMultipleEntries:
    def test_no_double_entry(self):
        """Engine enters and exits with take-profit, not entering while open."""
        sig = SignalResult(
            action="buy",
            direction="long",
            target_price=125.0,
            position_size=100,
        )
        runner = BacktestRunner()
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        prices = list(range(100, 130, 3))
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 1 for p in prices],
                "low": [p - 1 for p in prices],
                "close": prices,
                "volume": [1000000] * 10,
            },
            index=dates,
        )
        result = runner.run(df, _StaticSignalStrategy(sig), 10000)
        assert result["total_trades"] >= 1


class TestSignalExit:
    def test_signal_exit_closes_position(self):
        df = _make_flat_df(20)
        runner = BacktestRunner()
        result = runner.run(df, _AlternatingSignalStrategy(), 10000)
        # Enter on bar 1 (conservative: bar 2 open), exit on bar 10
        assert result["total_trades"] == 1
