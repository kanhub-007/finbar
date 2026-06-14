"""Tests for backtest_runner helpers (date precomputation, etc.)."""

import pandas as pd

from finbar.infrastructure.services.backtest_runner import _precompute_dates


class TestPrecomputeDates:
    def test_daily_dates_have_no_time_component(self):
        index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
        assert _precompute_dates(index) == [
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
        ]

    def test_intraday_dates_preserve_time(self):
        index = pd.to_datetime(
            ["2024-01-01 10:00:00", "2024-01-01 11:00:00"]
        )
        assert _precompute_dates(index) == [
            "2024-01-01T10:00:00",
            "2024-01-01T11:00:00",
        ]

    def test_mixed_date_and_datetime_within_one_index(self):
        # midnight (no time component) vs a later time
        index = pd.to_datetime(["2024-01-01 00:00:00", "2024-01-01 09:30:00"])
        result = _precompute_dates(index)
        assert result[0] == "2024-01-01"
        assert result[1] == "2024-01-01T09:30:00"

    def test_string_index_falls_back_to_str(self):
        index = pd.Index(["2024-01-01", "2024-01-02"])
        assert _precompute_dates(index) == ["2024-01-01", "2024-01-02"]

    def test_length_matches_index(self):
        index = pd.date_range("2024-01-01", periods=500, freq="D")
        dates = _precompute_dates(index)
        assert len(dates) == 500
