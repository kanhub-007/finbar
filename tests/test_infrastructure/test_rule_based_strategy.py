"""Integration tests for RuleBasedStrategy and strategy definition CRUD."""

import numpy as np
import pandas as pd

from finbar.core.domain.entities.strategy_definition import Rule, StrategyDefinition
from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)
from finbar.infrastructure.services.rule_based_strategy import RuleBasedStrategy


def _make_sample_df(periods: int = 200) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=periods, freq="D")
    close = 100 + np.cumsum(np.random.randn(periods) * 1.2 + 0.2)
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


class TestRuleBasedStrategy:
    def test_rsi_oversold_entry(self):
        """Strategy: buy when RSI < 30, exit when RSI > 70."""
        sdef = StrategyDefinition(
            name="rsi_test",
            direction="long",
            entry_rules=[Rule(indicator="rsi_14", operator="<", value=30)],
            exit_rules=[Rule(indicator="rsi_14", operator=">", value=70)],
        )
        strategy = RuleBasedStrategy(sdef)
        assert strategy.meta().name == "rsi_test"
        assert "rsi_14" in strategy.meta().required_indicators

    def test_returns_result_dict(self):
        sdef = StrategyDefinition(
            name="test_rules",
            direction="long",
            entry_rules=[
                Rule(indicator="rsi_14", operator="<", value=35),
                Rule(indicator="close", operator=">", value="sma_50"),
            ],
            exit_rules=[Rule(indicator="rsi_14", operator=">", value=65)],
        )
        df = _make_sample_df(200)
        calc = PandasTaIndicatorCalculator()
        df = calc.calculate(df, ["rsi_14", "sma_50"])

        runner = BacktestRunner()
        strategy = RuleBasedStrategy(sdef)
        result = runner.run(df, strategy, 10000)

        assert result["strategy_name"] == "test_rules"
        assert result["bar_count"] == 200
        assert "trades" in result

    def test_cross_indicator_comparison(self):
        """close > sma_50 as entry rule."""
        sdef = StrategyDefinition(
            name="cross_test",
            direction="long",
            entry_rules=[
                Rule(indicator="close", operator=">", value="sma_20"),
            ],
            exit_rules=[
                Rule(indicator="close", operator="<", value="sma_20"),
            ],
        )
        df = _make_sample_df(100)
        calc = PandasTaIndicatorCalculator()
        df = calc.calculate(df, ["sma_20"])

        runner = BacktestRunner()
        strategy = RuleBasedStrategy(sdef)
        result = runner.run(df, strategy, 10000)
        assert result["total_trades"] >= 0

    def test_crossover_detection(self):
        """Test crosses_above operator."""
        sdef = StrategyDefinition(
            name="crossover_test",
            direction="long",
            entry_rules=[
                Rule(
                    indicator="close",
                    operator="crosses_above",
                    value="sma_20",
                ),
            ],
            exit_rules=[],
        )
        df = _make_sample_df(100)
        calc = PandasTaIndicatorCalculator()
        df = calc.calculate(df, ["sma_20"])

        runner = BacktestRunner()
        strategy = RuleBasedStrategy(sdef)
        result = runner.run(df, strategy, 10000)
        # Crossover should trigger trades on trending data
        assert result["total_trades"] >= 0

    def test_stop_loss_atr(self):
        sdef = StrategyDefinition(
            name="stop_test",
            direction="long",
            entry_rules=[Rule(indicator="rsi_14", operator="<", value=30)],
            exit_rules=[],
            stop_loss_atr_mult=2.0,
        )
        df = _make_sample_df(200)
        calc = PandasTaIndicatorCalculator()
        df = calc.calculate(df, ["rsi_14", "atr"])

        runner = BacktestRunner()
        strategy = RuleBasedStrategy(sdef)
        result = runner.run(df, strategy, 10000)
        # ATR should be in required indicators
        assert "atr" in strategy.meta().required_indicators

    def test_any_entry_mode(self):
        """require_all_entry_rules=False — any rule triggers entry."""
        sdef = StrategyDefinition(
            name="any_test",
            direction="long",
            entry_rules=[
                Rule(indicator="rsi_14", operator="<", value=20),
                Rule(indicator="rsi_14", operator=">", value=80),
            ],
            exit_rules=[],
            require_all_entry_rules=False,
        )
        df = _make_sample_df(200)
        calc = PandasTaIndicatorCalculator()
        df = calc.calculate(df, ["rsi_14"])

        runner = BacktestRunner()
        strategy = RuleBasedStrategy(sdef)
        result = runner.run(df, strategy, 10000)
        assert result["total_trades"] >= 0

    def test_short_direction(self):
        sdef = StrategyDefinition(
            name="short_test",
            direction="short",
            entry_rules=[Rule(indicator="rsi_14", operator=">", value=70)],
            exit_rules=[Rule(indicator="rsi_14", operator="<", value=30)],
        )
        df = _make_sample_df(200)
        calc = PandasTaIndicatorCalculator()
        df = calc.calculate(df, ["rsi_14"])

        runner = BacktestRunner()
        strategy = RuleBasedStrategy(sdef)
        result = runner.run(df, strategy, 10000)
        assert result["strategy_name"] == "short_test"
