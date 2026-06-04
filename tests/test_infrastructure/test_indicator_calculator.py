"""Integration tests for PandasTaIndicatorCalculator with pandas_ta."""

import numpy as np
import pandas as pd

from finbar.infrastructure.services.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)


def _make_sample_df(periods: int = 100) -> pd.DataFrame:
    """Create a sample OHLCV DataFrame for testing."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=periods, freq="D")
    close = 100 + np.cumsum(np.random.randn(periods) * 1.5)
    return pd.DataFrame(
        {
            "open": close - np.random.rand(periods),
            "high": close + np.random.rand(periods) * 2,
            "low": close - np.random.rand(periods) * 2,
            "close": close,
            "volume": np.random.randint(100000, 1000000, periods),
        },
        index=dates,
    )


class TestPandasTaCalculator:
    def setup_method(self):
        self.calc = PandasTaIndicatorCalculator()

    def test_empty_df_returns_copy(self):
        df = pd.DataFrame()
        result = self.calc.calculate(df, ["rsi_14"])
        assert result.empty

    def test_empty_indicators_returns_copy(self):
        df = _make_sample_df()
        result = self.calc.calculate(df, [])
        assert len(result) == len(df)

    def test_rsi(self):
        df = _make_sample_df(50)
        result = self.calc.calculate(df, ["rsi_14"])
        assert "rsi_14" in result.columns
        assert result["rsi_14"].notna().any()

    def test_sma(self):
        df = _make_sample_df(250)
        result = self.calc.calculate(df, ["sma_20", "sma_50", "sma_200"])
        assert "sma_20" in result.columns
        assert "sma_200" in result.columns

    def test_macd(self):
        df = _make_sample_df(100)
        result = self.calc.calculate(df, ["macd", "macd_signal", "macd_hist"])
        assert "macd" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_hist" in result.columns

    def test_atr(self):
        df = _make_sample_df(50)
        result = self.calc.calculate(df, ["atr"])
        assert "atr" in result.columns

    def test_adx(self):
        df = _make_sample_df(50)
        result = self.calc.calculate(df, ["adx"])
        assert "adx" in result.columns

    def test_bb(self):
        df = _make_sample_df(50)
        result = self.calc.calculate(df, ["bb_upper", "bb_middle", "bb_lower"])
        assert "bb_upper" in result.columns

    def test_ibs_rvol(self):
        df = _make_sample_df(50)
        result = self.calc.calculate(df, ["ibs", "rvol"])
        assert "ibs" in result.columns
        assert "rvol" in result.columns

    def test_proxy_indicators(self):
        df = _make_sample_df(50)
        df = self.calc.calculate(df, ["atr"])  # ATR needed for IB proxies
        result = self.calc.calculate(df, ["proxy_typical_price", "proxy_ibs"])
        assert "proxy_typical_price" in result.columns
        # All proxies computed in batch
        assert "proxy_parkinson" in result.columns

    def test_trend_indicators(self):
        df = _make_sample_df(250)
        result = self.calc.calculate(
            df,
            [
                "sma_20",
                "sma_50",
                "sma_200",
                "adx",
                "trend_direction",
                "trend_strength",
                "trend_status",
            ],
        )
        assert "trend_direction" in result.columns
        assert set(result["trend_direction"].dropna().unique()) <= {
            "BULLISH",
            "BEARISH",
            "NEUTRAL",
        }

    def test_support_resistance(self):
        df = _make_sample_df(50)
        result = self.calc.calculate(
            df,
            [
                "swing_high_20",
                "swing_low_20",
                "breakout_level",
                "breakout_signal",
            ],
        )
        assert "swing_high_20" in result.columns
        assert "breakout_signal" in result.columns

    def test_unknown_indicator(self):
        df = _make_sample_df(50)
        result = self.calc.calculate(df, ["nonexistent_indicator"])
        # Should not crash — just skips unknown
        assert len(result) == len(df)

    def test_multiple_indicators_in_one_call(self):
        df = _make_sample_df(100)
        indicators = [
            "rsi_14",
            "sma_20",
            "sma_50",
            "atr",
            "macd",
            "ibs",
            "rvol",
        ]
        result = self.calc.calculate(df, indicators)
        for ind in indicators:
            assert ind in result.columns
