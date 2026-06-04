"""Unit tests for application use cases with mocked interfaces."""

from unittest.mock import MagicMock

import pandas as pd

from finbar.core.application.dto.apply_indicators_request import (
    ApplyIndicatorsRequest,
)
from finbar.core.application.dto.apply_indicators_result import (
    ApplyIndicatorsResult,
)
from finbar.core.application.use_cases.apply_indicators import (
    ApplyIndicatorsUseCase,
)


class StubIndicatorCalculator:
    """Stub that returns a DataFrame with a test column added."""

    def calculate(self, df: pd.DataFrame, indicators: list[str]) -> pd.DataFrame:
        result = df.copy()
        for ind in indicators:
            result[ind] = 1.0
        return result


class TestApplyIndicatorsUseCase:
    def setup_method(self):
        self.calculator = StubIndicatorCalculator()
        self.use_case = ApplyIndicatorsUseCase(self.calculator)

    def test_empty_bars_returns_error(self):
        result = self.use_case.execute(
            ApplyIndicatorsRequest(bars=[], indicators=["rsi_14"])
        )
        assert isinstance(result, ApplyIndicatorsResult)
        assert result.error is not None
        assert "No bars" in result.error

    def test_empty_indicators_returns_bars_unchanged(self):
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
            ApplyIndicatorsRequest(bars=bars, indicators=[])
        )
        assert result.error is None
        assert result.bar_count == 1
        assert result.indicators_applied == []

    def test_applies_indicators(self):
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
            ApplyIndicatorsRequest(bars=bars, indicators=["rsi_14", "sma_20"])
        )
        assert result.error is None
        assert result.bar_count == 1
        assert result.indicators_applied == ["rsi_14", "sma_20"]

    def test_missing_columns_returns_error(self):
        bars = [{"timestamp": "2024-01-01", "close": 100}]
        result = self.use_case.execute(
            ApplyIndicatorsRequest(bars=bars, indicators=["rsi_14"])
        )
        assert result.error is not None
        assert "Missing" in result.error
