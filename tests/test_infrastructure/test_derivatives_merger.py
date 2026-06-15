"""Tests for derivatives merger — Scenario 5.1 (no lookahead).

Verifies merge_derivatives_asof joins derivatives data onto OHLCV bars
with the no-lookahead invariant: a value timestamped T is only visible
at bar T+1 or later.
"""

import numpy as np
import pandas as pd
import pytest

from finbar.core.domain.entities.derivatives_metrics import DerivativesMetrics
from finbar.infrastructure.services.derivatives_merger import merge_derivatives_asof


class TestNoLookaheadMerge:
    """Derivatives values must not leak into earlier bars."""

    def test_funding_visible_at_next_bar_not_same_bar(self):
        """Funding stamped 10:00 must appear on 11:00 bar, not 10:00."""
        ohlcv = pd.DataFrame(
            {"close": [100.0] * 4},
            index=pd.date_range("2024-01-01 10:00", periods=4, freq="1h"),
        )
        funding_rows = [
            DerivativesMetrics(
                symbol="BTC",
                timestamp="2024-01-01T10:00:00+00:00",
                interval="1h",
                funding_rate=0.0001,
            ),
            DerivativesMetrics(
                symbol="BTC",
                timestamp="2024-01-01T11:00:00+00:00",
                interval="1h",
                funding_rate=0.0002,
            ),
            DerivativesMetrics(
                symbol="BTC",
                timestamp="2024-01-01T12:00:00+00:00",
                interval="1h",
                funding_rate=0.0003,
            ),
        ]
        result = merge_derivatives_asof(ohlcv, funding_rows, interval="1h")

        assert "funding_rate" in result.columns
        # No lookahead: 10:00 bar must NOT see 10:00 funding
        assert pd.isna(result.loc[result.index[0], "funding_rate"])
        # 11:00 bar sees 10:00 funding
        assert abs(result.loc[result.index[1], "funding_rate"] - 0.0001) < 1e-9
        # 12:00 bar sees 11:00 funding
        assert abs(result.loc[result.index[2], "funding_rate"] - 0.0002) < 1e-9

    def test_empty_funding_list_produces_nan_columns(self):
        """Empty derivatives list → all-NaN columns, no crash."""
        ohlcv = pd.DataFrame(
            {"close": [100.0] * 3},
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        )
        result = merge_derivatives_asof(ohlcv, [], interval="1d")

        assert "funding_rate" in result.columns
        assert result["funding_rate"].isna().all()
        assert "open_interest" in result.columns
        assert result["open_interest"].isna().all()

    def test_forward_fill_for_gaps(self):
        """Missing hours forward-fill from the latest available."""
        ohlcv = pd.DataFrame(
            {"close": [100.0] * 5},
            index=pd.date_range("2024-01-01 10:00", periods=5, freq="1h"),
        )
        # Only one funding row at 10:00, visible from 11:00 onward
        funding_rows = [
            DerivativesMetrics(
                symbol="BTC",
                timestamp="2024-01-01T10:00:00+00:00",
                interval="1h",
                funding_rate=0.0005,
            ),
        ]
        result = merge_derivatives_asof(ohlcv, funding_rows, interval="1h")

        # 10:00 bar: NaN (no prior data)
        assert pd.isna(result.loc[result.index[0], "funding_rate"])
        # 11:00 onward: 0.0005 (forward-filled)
        assert abs(result.loc[result.index[1], "funding_rate"] - 0.0005) < 1e-9
        assert abs(result.loc[result.index[4], "funding_rate"] - 0.0005) < 1e-9

    def test_daily_offset_on_intraday_bars(self):
        """Daily derivatives merged onto hourly bars use +1d offset."""
        ohlcv = pd.DataFrame(
            {"close": [100.0] * 48},
            index=pd.date_range("2024-01-01 00:00", periods=48, freq="1h"),
        )
        daily_funding = [
            DerivativesMetrics(
                symbol="BTC",
                timestamp="2024-01-01T00:00:00+00:00",
                interval="1d",
                funding_rate=0.001,
            ),
        ]
        result = merge_derivatives_asof(ohlcv, daily_funding, interval="1d")

        # Daily data stamped Jan 1 00:00 → visible at Jan 2 00:00 (bar 24)
        assert pd.isna(result.loc[result.index[0], "funding_rate"])
        assert abs(result.loc[result.index[24], "funding_rate"] - 0.001) < 1e-9

    def test_original_ohlcv_columns_preserved(self):
        """Original OHLCV columns must remain intact after merge."""
        ohlcv = pd.DataFrame(
            {
                "open": [1.0, 2.0],
                "high": [1.5, 2.5],
                "low": [0.5, 1.5],
                "close": [1.2, 2.2],
                "volume": [100.0, 200.0],
            },
            index=pd.date_range("2024-01-01", periods=2, freq="D"),
        )
        result = merge_derivatives_asof(ohlcv, [], interval="1d")

        for col in ["open", "high", "low", "close", "volume"]:
            assert col in result.columns
            assert result[col].equals(ohlcv[col])

    def test_multiple_derivatives_columns(self):
        """Multiple fields (funding + OI) merge in one call."""
        ohlcv = pd.DataFrame(
            {"close": [100.0] * 3},
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        )
        rows = [
            DerivativesMetrics(
                symbol="BTC",
                timestamp="2024-01-01T00:00:00+00:00",
                interval="1d",
                funding_rate=0.0001,
                open_interest=1_500_000,
            ),
        ]
        result = merge_derivatives_asof(ohlcv, rows, interval="1d")

        assert "funding_rate" in result.columns
        assert "open_interest" in result.columns
        # Bar 1 sees the Jan 1 data
        assert abs(result.loc[result.index[1], "funding_rate"] - 0.0001) < 1e-9
        assert abs(result.loc[result.index[1], "open_interest"] - 1_500_000) < 1


class TestTimezoneNormalization:
    def test_both_aware_different_timezones_aligns_instants(self):
        """OHLCV index and derivatives rows both tz-aware but in different
        zones must be reconciled (tz_convert) rather than crashing or
        silently misaligning. A UTC funding value at midnight must appear on
        the next UTC-midnight OHLCV bar even when the OHLCV index is, e.g.,
        US/Eastern-aware."""
        import zoneinfo

        eastern = zoneinfo.ZoneInfo("America/New_York")
        # OHLCV bars at US/Eastern midnight: 2024-01-01 00:00 ET == 05:00 UTC.
        ohlcv = pd.DataFrame(
            {"close": [100.0] * 3},
            index=pd.date_range("2024-01-01", periods=3, freq="D").tz_localize(eastern),
        )
        # Derivatives row stamped midnight UTC on Jan 1.
        rows = [
            DerivativesMetrics(
                symbol="BTC",
                timestamp="2024-01-01T00:00:00+00:00",
                interval="1d",
                funding_rate=0.0001,
            ),
        ]
        result = merge_derivatives_asof(ohlcv, rows, interval="1d")
        # The funding value (available at Jan 2 00:00 UTC == Jan 1 19:00 ET)
        # must have been forward-filled onto at least one later bar.
        assert result["funding_rate"].notna().any()
        # And it must NOT leak onto the very first bar (no-lookahead).
        assert pd.isna(result["funding_rate"].iloc[0])
