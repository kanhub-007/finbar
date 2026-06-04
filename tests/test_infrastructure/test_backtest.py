"""Integration tests for BacktestRunner, strategies, and bar merger."""

import numpy as np
import pandas as pd

from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.backtest_strategies.rsi_mean_reversion import (
    RsiMeanReversionStrategy,
)
from finbar.infrastructure.services.backtest_strategies.sma_crossover import (
    SmaCrossoverStrategy,
)
from finbar.infrastructure.services.bar_merger import merge_timeframes
from finbar.infrastructure.services.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)


def _make_trending_df(periods: int = 200) -> pd.DataFrame:
    """Create a trending OHLCV DataFrame (mostly up)."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=periods, freq="D")
    # Strong upward drift
    close = 100 + np.cumsum(np.random.randn(periods) * 0.8 + 0.3)
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


class TestSmaCrossover:
    def test_returns_result_dict(self):
        df = _make_trending_df(200)
        calc = PandasTaIndicatorCalculator()
        df = calc.calculate(df, ["sma_20", "sma_50"])

        runner = BacktestRunner()
        result = runner.run(df, SmaCrossoverStrategy(), 10000)

        assert "strategy_name" in result
        assert result["strategy_name"] == "sma_crossover"
        assert result["bar_count"] == 200
        assert result["initial_cash"] == 10000
        assert "trades" in result
        assert "equity_curve" in result
        assert len(result["equity_curve"]) == 200

    def test_empty_df_returns_error(self):
        runner = BacktestRunner()
        result = runner.run(pd.DataFrame(), SmaCrossoverStrategy(), 10000)
        assert "error" in result

    def test_handles_multiple_runs(self):
        df = _make_trending_df(100)
        calc = PandasTaIndicatorCalculator()
        df = calc.calculate(df, ["sma_20", "sma_50"])

        runner = BacktestRunner()
        r1 = runner.run(df, SmaCrossoverStrategy(), 10000)
        r2 = runner.run(df, SmaCrossoverStrategy(), 10000)
        # Same input, same output
        assert r1["total_return"] == r2["total_return"]


class TestRsiMeanReversion:
    def test_returns_result(self):
        df = _make_trending_df(200)
        calc = PandasTaIndicatorCalculator()
        df = calc.calculate(df, ["rsi_14"])

        runner = BacktestRunner()
        result = runner.run(df, RsiMeanReversionStrategy(), 10000)

        assert result["strategy_name"] == "rsi_mean_reversion"
        assert result["bar_count"] == 200


class TestBacktestMetricFields:
    def test_all_required_fields_present(self):
        df = _make_trending_df(200)
        calc = PandasTaIndicatorCalculator()
        df = calc.calculate(df, ["sma_20", "sma_50"])

        runner = BacktestRunner()
        result = runner.run(df, SmaCrossoverStrategy(), 10000)

        required = {
            "strategy_name",
            "start_date",
            "end_date",
            "bar_count",
            "initial_cash",
            "final_value",
            "total_return",
            "total_trades",
            "winning_trades",
            "losing_trades",
            "win_rate",
            "max_drawdown",
            "sharpe_ratio",
            "sortino_ratio",
            "profit_factor",
            "calmar_ratio",
            "trades",
            "equity_curve",
        }
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_trade_record_format(self):
        df = _make_trending_df(200)
        calc = PandasTaIndicatorCalculator()
        df = calc.calculate(df, ["sma_20", "sma_50"])

        runner = BacktestRunner()
        result = runner.run(df, SmaCrossoverStrategy(), 10000)

        for trade in result["trades"]:
            assert "entry_date" in trade
            assert "exit_date" in trade
            assert "entry_price" in trade
            assert "exit_price" in trade
            assert "pnl" in trade
            assert "pnl_pct" in trade


class TestBarMerger:
    def test_merges_columns_with_suffix(self):
        daily = pd.DataFrame(
            {
                "sma_50": [105.0, 106.0],
                "sma_200": [100.0, 101.0],
                "atr": [2.5, 2.3],
            },
            index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
        )

        hourly = pd.DataFrame(
            {
                "open": [101, 102, 103],
                "high": [104, 105, 106],
                "low": [100, 101, 102],
                "close": [103, 104, 105],
                "volume": [5000, 6000, 7000],
            },
            index=pd.to_datetime(
                [
                    "2024-01-01 10:00",
                    "2024-01-01 11:00",
                    "2024-01-02 10:00",
                ]
            ),
        )

        merged = merge_timeframes(hourly, daily, "1d")
        assert "sma_50_1d" in merged.columns
        assert "sma_200_1d" in merged.columns
        assert "atr_1d" in merged.columns
        # OHLCV should not be merged
        assert "open_1d" not in merged.columns
        # Original columns preserved
        assert "open" in merged.columns
        assert len(merged) == 3

    def test_handles_empty_informative(self):
        primary = _make_trending_df(10)
        merged = merge_timeframes(primary, pd.DataFrame(), "1d")
        assert len(merged) == len(primary)

    def test_specific_columns(self):
        daily = pd.DataFrame(
            {
                "sma_50": [105.0],
                "sma_200": [100.0],
                "atr": [2.5],
            },
            index=pd.to_datetime(["2024-01-01"]),
        )
        hourly = pd.DataFrame(
            {
                "open": [101],
                "high": [104],
                "low": [100],
                "close": [103],
                "volume": [5000],
            },
            index=pd.to_datetime(["2024-01-01 10:00"]),
        )
        merged = merge_timeframes(hourly, daily, "1d", columns=["sma_50"])
        assert "sma_50_1d" in merged.columns
        assert "sma_200_1d" not in merged.columns
        assert "atr_1d" not in merged.columns
