"""Contract tests for rolling_scalar_wrapper — Scenario 1.2.

Verifies the rolling-window wrapper converts a scalar calculator
into a per-bar Series with proper warm-up handling.
"""

import numpy as np
import pandas as pd

from finbar_strategy_runtime.domain.services.spread_proxies import roll_spread
from finbar_strategy_runtime.indicators.rolling_scalar_wrapper import (
    rolling_scalar_series,
)


class TestRollingScalarSeries:
    """Verify rolling_scalar_series converts a scalar calculator to a Series."""

    def test_returns_series_of_same_length(self):
        """Result length must match input length."""
        np.random.seed(1)
        close = pd.Series(100 + np.cumsum(np.random.randn(40) * 0.5))
        result = rolling_scalar_series(roll_spread, close, window=20)

        assert isinstance(result, pd.Series)
        assert len(result) == len(close)

    def test_warmup_period_is_nan(self):
        """Bars before window-1 must be NaN (not enough data yet)."""
        np.random.seed(1)
        close = pd.Series(100 + np.cumsum(np.random.randn(40) * 0.5))
        result = rolling_scalar_series(roll_spread, close, window=20)

        assert result.iloc[:19].isna().all()

    def test_first_value_after_warmup_is_finite(self):
        """The bar at index window-1 must have a finite value."""
        np.random.seed(1)
        close = pd.Series(100 + np.cumsum(np.random.randn(40) * 0.5))
        result = rolling_scalar_series(roll_spread, close, window=20)

        assert np.isfinite(result.iloc[-1])

    def test_index_aligned_with_input(self):
        """The result index must match the input index."""
        np.random.seed(1)
        idx = pd.date_range("2024-01-01", periods=30, freq="D")
        close = pd.Series(100 + np.cumsum(np.random.randn(30) * 0.5), index=idx)
        result = rolling_scalar_series(roll_spread, close, window=20)

        assert result.index.equals(close.index)

    def test_window_larger_than_data_all_nan(self):
        """When window > len(data), all values must be NaN (no crash)."""
        close = pd.Series([100.0, 101.0, 102.0])
        result = rolling_scalar_series(roll_spread, close, window=20)

        assert len(result) == 3
        assert result.isna().all()

    def test_window_boundary_exact(self):
        """Exactly `window` bars → first non-NaN at index window-1."""
        np.random.seed(2)
        close = pd.Series(100 + np.cumsum(np.random.randn(20) * 0.5))
        result = rolling_scalar_series(roll_spread, close, window=20)

        # First 19 bars NaN, bar at index 19 must be finite
        assert result.iloc[:19].isna().all()
        assert np.isfinite(result.iloc[19])

    def test_calculator_returns_none_yields_nan(self):
        """When the calculator returns None for a window, that bar is NaN."""

        def always_none(window_slice: pd.Series) -> float | None:
            return None

        close = pd.Series(np.arange(30, dtype=float))
        result = rolling_scalar_series(always_none, close, window=5)

        assert result.isna().all()

    def test_calculator_raises_yields_nan(self):
        """When the calculator raises, that bar is NaN (no crash)."""

        def always_raise(window_slice: pd.Series) -> float:
            raise ValueError("boom")

        close = pd.Series(np.arange(30, dtype=float))
        result = rolling_scalar_series(always_raise, close, window=5)

        assert result.isna().all()

    def test_passes_kwargs_to_calculator(self):
        """Extra kwargs must be forwarded to the calculator."""
        captured: list[int] = []

        def capturing_calc(window_slice: pd.Series, lookback: int = 20) -> float:
            captured.append(lookback)
            return float(window_slice.iloc[-1])

        close = pd.Series(np.arange(30, dtype=float))
        rolling_scalar_series(capturing_calc, close, window=5, lookback=99)

        assert all(k == 99 for k in captured)
