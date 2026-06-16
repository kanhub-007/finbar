"""first_last_hour_vol_fraction proxy tests — spec 2026-06-16 Scenario 12.

The metric originally required ``opening_volume``/``closing_volume``
columns that no OHLCV data source provides (Scenario 2 marked it
unavailable). This proxy replaces that requirement: it groups intraday
bars by UTC date and sums volume for the first and last hour of each
day, divided by the daily total. No external columns needed.

Classical school: pure function + real calculator dispatch. No mocks.
"""

import numpy as np
import pandas as pd
import pytest

from finbar_strategy_runtime.domain.services.intraday_seasonality_proxies import (
    first_last_hour_vol_fraction_proxy,
)
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)


def _intraday_df(days: int = 5, hours_per_day: int = 24, seed: int = 1) -> pd.DataFrame:
    """Build ``days`` UTC days of ``hours_per_day`` hourly bars."""
    rng = np.random.default_rng(seed)
    n = days * hours_per_day
    idx = pd.date_range("2026-01-05", periods=n, freq="1h")  # UTC, tz-naive
    close = 100.0 + rng.uniform(-1.0, 1.0, n).cumsum()
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": rng.integers(100, 1000, n).astype(float),
        },
        index=idx,
    )


class TestFirstLastHourVolFractionProxy:
    """Scenario 12 — intraday UTC-day grouping proxy."""

    def test_returns_series_with_non_null_values(self):
        result = first_last_hour_vol_fraction_proxy(_intraday_df())
        assert isinstance(result, pd.Series)
        assert result.notna().any()

    def test_values_in_zero_to_one_range(self):
        result = first_last_hour_vol_fraction_proxy(_intraday_df())
        non_null = result.dropna()
        assert (non_null >= 0).all()
        assert (non_null <= 1).all()

    def test_sums_first_and_last_hour_divided_by_daily_total(self):
        """A hand-computed fixture: known volume at hour 0 and hour 23."""
        # One day, 3 bars at hours 0, 12, 23 with volumes 100, 200, 50.
        idx = pd.to_datetime(
            ["2026-01-05 00:00", "2026-01-05 12:00", "2026-01-05 23:00"]
        )
        df = pd.DataFrame(
            {"volume": [100.0, 200.0, 50.0]},
            index=idx,
        )
        result = first_last_hour_vol_fraction_proxy(df)
        # first hour (0) vol=100, last hour (23) vol=50, total=350 → 150/350
        assert result.notna().all()
        for v in result:
            assert abs(v - (100.0 + 50.0) / 350.0) < 1e-9

    def test_daily_data_returns_nan(self):
        """Daily bars cannot be subdivided into first/last hour → NaN."""
        idx = pd.date_range("2026-01-05", periods=30, freq="D")
        df = pd.DataFrame(
            {"volume": np.full(30, 1_000_000.0)},
            index=idx,
        )
        result = first_last_hour_vol_fraction_proxy(df)
        assert result.isna().all()

    def test_zero_volume_day_is_nan_not_inf(self):
        """Division by zero daily total must yield NaN, not inf."""
        idx = pd.date_range("2026-01-05 00:00", periods=24, freq="1h")
        df = pd.DataFrame({"volume": np.zeros(24)}, index=idx)
        result = first_last_hour_vol_fraction_proxy(df)
        assert not result.isin([np.inf, -np.inf]).any()


class TestFirstLastHourVolFractionViaDispatch:
    """Scenario 12 — the handler dispatches to the proxy on intraday data."""

    def test_column_present_and_bounded_on_intraday(self):
        calc = PandasTaIndicatorCalculator()
        result = calc.calculate(_intraday_df(), ["first_last_hour_vol_fraction"])
        assert "first_last_hour_vol_fraction" in result.columns
        non_null = result["first_last_hour_vol_fraction"].dropna()
        assert len(non_null) > 0
        assert (non_null >= 0).all() and (non_null <= 1).all()
