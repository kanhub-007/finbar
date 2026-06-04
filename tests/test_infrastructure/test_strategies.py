"""Tests for AuctionDriveStrategy and MomentumBreakoutStrategy."""

import numpy as np
import pandas as pd

from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.backtest_strategies.auction_drive import (
    AuctionDriveStrategy,
)
from finbar.infrastructure.services.backtest_strategies.momentum_breakout import (
    MomentumBreakoutStrategy,
)
from finbar.infrastructure.services.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)


def _make_df(periods: int, drift: float = 0.2) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=periods, freq="D")
    close = 100 + np.cumsum(np.random.randn(periods) * 1.2 + drift)
    return pd.DataFrame(
        {
            "open": close - np.random.rand(periods) * 0.5,
            "high": close + np.random.rand(periods),
            "low": close - np.random.rand(periods),
            "close": close,
            "volume": np.random.randint(100000, 1000000, periods),
        },
        index=dates,
    )


class TestAuctionDriveStrategy:
    def setup_method(self):
        self.calc = PandasTaIndicatorCalculator()
        self.runner = BacktestRunner()

    def test_returns_valid_result(self):
        df = _make_df(200)
        indicators = [
            "atr",
            "vwap",
            "ibs",
            "rvol",
            "sma_50",
            "sma_200",
        ]
        df = self.calc.calculate(df, indicators)
        strat = AuctionDriveStrategy()
        result = self.runner.run(df, strat, 10000)
        assert result["strategy_name"] == "auction_drive"
        assert result["bar_count"] == 200
        assert "trades" in result
        assert "equity_curve" in result

    def test_meta_reflects_params(self):
        strat = AuctionDriveStrategy(sma_fast=20, sma_slow=100)
        meta = strat.meta()
        assert "sma_20" in meta.required_indicators
        assert "sma_100" in meta.required_indicators
        assert meta.params["sma_fast"] == 20

    def test_on_reset_clears_state(self):
        df = _make_df(100)
        indicators = ["atr", "vwap", "ibs", "rvol", "sma_50", "sma_200"]
        df = self.calc.calculate(df, indicators)
        strat = AuctionDriveStrategy()
        # Run once to accumulate state
        self.runner.run(df, strat, 10000)
        strat.on_reset()
        # After reset, rolling histories should be empty
        assert len(strat._close_history) == 0
        assert strat._atr_count == 0
        assert len(strat._volume_history) == 0

    def test_disallow_short_by_default(self):
        """Short trades should be disabled by default."""
        df = _make_df(200, drift=-0.3)  # downtrend
        indicators = [
            "atr",
            "vwap",
            "ibs",
            "rvol",
            "sma_50",
            "sma_200",
        ]
        df = self.calc.calculate(df, indicators)
        strat = AuctionDriveStrategy()
        result = self.runner.run(df, strat, 10000)
        # Check no short trades in metadata
        for trade in result["trades"]:
            meta = trade.get("metadata", {})
            assert meta.get("direction") != "short" or meta.get(
                "reason", ""
            ).startswith("auction_drive_long")

    def test_allow_short(self):
        strat = AuctionDriveStrategy(allow_short=True)
        assert strat._p["allow_short"] is True

    def test_empty_bars_handled(self):
        strat = AuctionDriveStrategy()
        sig = strat.on_bar({}, {"size": 0})
        assert sig.action == "hold"

    def test_ib_proxy_fallback(self):
        """When ib_high/ib_low not in bar, uses proxy."""
        df = _make_df(50)
        df = self.calc.calculate(df, ["atr"])
        strat = AuctionDriveStrategy()
        bar = df.iloc[-1].to_dict()
        sig = strat.on_bar(bar, {"size": 0})
        assert sig.action in ("buy", "sell", "hold")

    def test_vwap_proxy_fallback(self):
        """When vwap not in bar, uses typical_price proxy."""
        df = _make_df(50)
        df = self.calc.calculate(df, ["atr", "ibs", "rvol", "sma_50", "sma_200"])
        strat = AuctionDriveStrategy()
        bar = df.iloc[-1].to_dict()
        sig = strat.on_bar(bar, {"size": 0})
        # Should not crash
        assert sig is not None

    def test_multiple_runs_same_result(self):
        df = _make_df(100)
        indicators = ["atr", "vwap", "ibs", "rvol", "sma_50", "sma_200"]
        df = self.calc.calculate(df, indicators)
        r1 = self.runner.run(df, AuctionDriveStrategy(), 10000)
        r2 = self.runner.run(df, AuctionDriveStrategy(), 10000)
        assert r1["total_return"] == r2["total_return"]


class TestMomentumBreakout:
    def setup_method(self):
        self.calc = PandasTaIndicatorCalculator()
        self.runner = BacktestRunner()

    def test_returns_valid_result(self):
        df = _make_df(200)
        df = self.calc.calculate(df, ["sma_50", "sma_200", "atr", "swing_high_20"])
        strat = MomentumBreakoutStrategy()
        result = self.runner.run(df, strat, 10000)
        assert result["strategy_name"] == "momentum_breakout"
        assert result["bar_count"] == 200

    def test_meta_reflects_params(self):
        strat = MomentumBreakoutStrategy(breakout_period=10, trend_sma=100, exit_sma=30)
        meta = strat.meta()
        assert "sma_100" in meta.required_indicators
        assert "sma_30" in meta.required_indicators

    def test_empty_bar_returns_hold(self):
        strat = MomentumBreakoutStrategy()
        sig = strat.on_bar({}, {"size": 0})
        assert sig.action == "hold"

    def test_exits_on_sma_cross(self):
        strat = MomentumBreakoutStrategy(exit_sma=50)
        bar = {
            "close": 95,
            "high": 100,
            "sma_50": 100,
            "sma_200": 90,
            "atr": 2.0,
        }
        sig = strat.on_bar(bar, {"size": 100, "direction": "long"})
        assert sig.action == "sell"
        assert sig.direction == "exit"

    def test_entry_above_swing_high(self):
        strat = MomentumBreakoutStrategy(breakout_period=20)
        bar = {
            "close": 110,
            "high": 108,
            "sma_200": 100,
            "sma_50": 105,
            "swing_high_20": 109,
            "atr": 2.0,
        }
        sig = strat.on_bar(bar, {"size": 0})
        assert sig.action == "buy"
        assert sig.metadata.get("reason") == "momentum_breakout"

    def test_entry_fallback_bar_high(self):
        """When swing_high_N missing, falls back to bar's own high."""
        strat = MomentumBreakoutStrategy(breakout_period=20)
        bar = {
            "close": 110,
            "high": 108,
            "sma_200": 100,
            "sma_50": 105,
            "atr": 2.0,
        }
        sig = strat.on_bar(bar, {"size": 0})
        assert sig.action == "buy"
        assert sig.metadata.get("reason") == "momentum_breakout_bar"
