"""Unit tests for IntrabarExitResolver — pure gap-aware stop/target logic."""

from finbar.infrastructure.services.backtest_position import BacktestPosition
from finbar.infrastructure.services.intrabar_exit_resolver import (
    IntrabarExitResolver,
)


def _long_pos(stop: float = 95.0, target: float = 110.0) -> BacktestPosition:
    pos = BacktestPosition()
    pos.size = 10.0
    pos.direction = "long"
    pos.stop_price = stop
    pos.target_price = target
    return pos


def _short_pos(stop: float = 105.0, target: float = 90.0) -> BacktestPosition:
    pos = BacktestPosition()
    pos.size = -10.0
    pos.direction = "short"
    pos.stop_price = stop
    pos.target_price = target
    return pos


class TestLongResolve:
    def test_no_trigger_when_price_ranges_safely(self):
        fill = IntrabarExitResolver.resolve(
            _long_pos(), open_price=100, high=105, low=99
        )
        assert fill is None

    def test_stop_loss_normal_fill(self):
        exit_price, reason = IntrabarExitResolver.resolve(
            _long_pos(stop=95), open_price=100, high=100, low=94
        )
        assert exit_price == 95.0
        assert reason == "stop_loss"

    def test_stop_loss_gap_fill(self):
        exit_price, reason = IntrabarExitResolver.resolve(
            _long_pos(stop=95), open_price=90, high=92, low=88
        )
        assert exit_price == 90.0
        assert reason == "stop_loss_gap"

    def test_take_profit_normal_fill(self):
        exit_price, reason = IntrabarExitResolver.resolve(
            _long_pos(target=110), open_price=108, high=112, low=108
        )
        assert exit_price == 110.0
        assert reason == "take_profit"

    def test_take_profit_gap_fill(self):
        exit_price, reason = IntrabarExitResolver.resolve(
            _long_pos(target=110), open_price=115, high=116, low=114
        )
        assert exit_price == 115.0
        assert reason == "take_profit_gap"

    def test_same_bar_stop_and_target_stop_wins(self):
        exit_price, reason = IntrabarExitResolver.resolve(
            _long_pos(stop=95, target=110), open_price=100, high=115, low=90
        )
        assert exit_price == 95.0
        assert reason == "stop_loss"

    def test_gap_below_stop_wins_over_target_gap(self):
        exit_price, reason = IntrabarExitResolver.resolve(
            _long_pos(stop=95, target=110), open_price=90, high=115, low=85
        )
        assert exit_price == 90.0
        assert reason == "stop_loss_gap"


class TestShortResolve:
    def test_no_trigger_when_price_ranges_safely(self):
        fill = IntrabarExitResolver.resolve(
            _short_pos(), open_price=100, high=101, low=95
        )
        assert fill is None

    def test_stop_loss_normal_fill(self):
        exit_price, reason = IntrabarExitResolver.resolve(
            _short_pos(stop=105), open_price=100, high=106, low=100
        )
        assert exit_price == 105.0
        assert reason == "stop_loss"

    def test_stop_loss_gap_fill(self):
        exit_price, reason = IntrabarExitResolver.resolve(
            _short_pos(stop=105), open_price=110, high=112, low=108
        )
        assert exit_price == 110.0
        assert reason == "stop_loss_gap"

    def test_take_profit_normal_fill(self):
        exit_price, reason = IntrabarExitResolver.resolve(
            _short_pos(target=90), open_price=95, high=95, low=88
        )
        assert exit_price == 90.0
        assert reason == "take_profit"

    def test_take_profit_gap_fill(self):
        exit_price, reason = IntrabarExitResolver.resolve(
            _short_pos(target=90), open_price=85, high=87, low=84
        )
        assert exit_price == 85.0
        assert reason == "take_profit_gap"

    def test_same_bar_stop_and_target_stop_wins(self):
        exit_price, reason = IntrabarExitResolver.resolve(
            _short_pos(stop=105, target=90), open_price=100, high=110, low=85
        )
        assert exit_price == 105.0
        assert reason == "stop_loss"


class TestFlatPosition:
    def test_flat_position_returns_none(self):
        pos = BacktestPosition()
        pos.size = 0.0

        fill = IntrabarExitResolver.resolve(pos, open_price=100, high=105, low=95)

        assert fill is None
