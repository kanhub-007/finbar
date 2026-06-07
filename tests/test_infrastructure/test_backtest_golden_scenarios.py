"""Golden scenario tests for exact backtest fills, PnL, and equity."""

import pandas as pd

from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.backtest_runner import BacktestRunner


class _OneShotEntryStrategy(TradingStrategy):
    """Emit one entry signal, then hold."""

    def __init__(self, signal: SignalResult):
        self._signal = signal
        self._emitted = False

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="golden_one_shot",
            variant=DataMode.REAL,
            description="Golden scenario helper",
            required_indicators=[],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        if not self._emitted and float(position.get("size", 0) or 0) == 0:
            self._emitted = True
            return self._signal
        return SignalResult(action="hold")

    def on_reset(self) -> None:
        self._emitted = False


def _bars(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """Build an OHLCV frame from date/open/high/low/close rows."""
    return pd.DataFrame(
        {
            "open": [row[1] for row in rows],
            "high": [row[2] for row in rows],
            "low": [row[3] for row in rows],
            "close": [row[4] for row in rows],
            "volume": [1000000] * len(rows),
        },
        index=pd.to_datetime([row[0] for row in rows]),
    )


def _run(signal: SignalResult, rows: list[tuple[str, float, float, float, float]]):
    """Run a one-shot strategy against rows."""
    return BacktestRunner().run(_bars(rows), _OneShotEntryStrategy(signal), 10000)


def test_long_next_open_entry_and_final_close_liquidation():
    result = _run(
        SignalResult(action="buy", direction="long", position_size=10),
        [
            ("2024-01-01", 100, 100, 100, 100),
            ("2024-01-02", 101, 101, 101, 101),
            ("2024-01-03", 102, 110, 102, 110),
        ],
    )

    trade = result["trades"][0]
    assert trade["entry_date"] == "2024-01-02"
    assert trade["entry_price"] == 101
    assert trade["exit_price"] == 110
    assert trade["pnl"] == 90
    assert result["final_value"] == 10090


def test_short_next_open_entry_and_final_close_cover():
    result = _run(
        SignalResult(action="sell", direction="short", position_size=10),
        [
            ("2024-01-01", 100, 100, 100, 100),
            ("2024-01-02", 100, 100, 100, 100),
            ("2024-01-03", 90, 90, 90, 90),
        ],
    )

    trade = result["trades"][0]
    assert trade["metadata"]["direction"] == "short"
    assert trade["entry_price"] == 100
    assert trade["exit_price"] == 90
    assert trade["pnl"] == 100
    assert result["final_value"] == 10100


def test_long_normal_stop_fills_at_stop_price():
    result = _run(
        SignalResult(action="buy", direction="long", position_size=10, stop_price=95),
        [
            ("2024-01-01", 100, 100, 100, 100),
            ("2024-01-02", 100, 100, 100, 100),
            ("2024-01-03", 100, 100, 94, 96),
        ],
    )

    trade = result["trades"][0]
    assert trade["exit_price"] == 95
    assert trade["pnl"] == -50
    assert trade["metadata"]["exit_reason"] == "stop_loss"
    assert result["final_value"] == 9950


def test_long_gap_stop_fills_at_gap_open():
    result = _run(
        SignalResult(action="buy", direction="long", position_size=10, stop_price=95),
        [
            ("2024-01-01", 100, 100, 100, 100),
            ("2024-01-02", 100, 100, 100, 100),
            ("2024-01-03", 90, 91, 89, 90),
        ],
    )

    trade = result["trades"][0]
    assert trade["exit_price"] == 90
    assert trade["pnl"] == -100
    assert trade["metadata"]["exit_reason"] == "stop_loss_gap"
    assert result["final_value"] == 9900


def test_short_normal_stop_fills_at_stop_price():
    result = _run(
        SignalResult(
            action="sell", direction="short", position_size=10, stop_price=105
        ),
        [
            ("2024-01-01", 100, 100, 100, 100),
            ("2024-01-02", 100, 100, 100, 100),
            ("2024-01-03", 100, 106, 100, 104),
        ],
    )

    trade = result["trades"][0]
    assert trade["exit_price"] == 105
    assert trade["pnl"] == -50
    assert trade["metadata"]["exit_reason"] == "stop_loss"
    assert result["final_value"] == 9950


def test_long_target_gap_fills_at_better_open():
    result = _run(
        SignalResult(
            action="buy", direction="long", position_size=10, target_price=110
        ),
        [
            ("2024-01-01", 100, 100, 100, 100),
            ("2024-01-02", 100, 100, 100, 100),
            ("2024-01-03", 115, 116, 115, 115),
        ],
    )

    trade = result["trades"][0]
    assert trade["exit_price"] == 115
    assert trade["pnl"] == 150
    assert trade["metadata"]["exit_reason"] == "take_profit_gap"
    assert result["final_value"] == 10150


def test_same_bar_stop_target_collision_uses_stop_first():
    result = _run(
        SignalResult(
            action="buy",
            direction="long",
            position_size=10,
            stop_price=95,
            target_price=110,
        ),
        [
            ("2024-01-01", 100, 100, 100, 100),
            ("2024-01-02", 100, 100, 100, 100),
            ("2024-01-03", 100, 115, 90, 100),
        ],
    )

    trade = result["trades"][0]
    assert trade["exit_price"] == 95
    assert trade["pnl"] == -50
    assert trade["metadata"]["exit_reason"] == "stop_loss"
    assert result["final_value"] == 9950
