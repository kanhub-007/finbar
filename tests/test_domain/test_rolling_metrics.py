"""Unit tests for rolling_metrics domain service."""

import pytest

from finbar.core.domain.services.rolling_metrics import (
    calculate_exposure,
    calculate_monthly_returns,
    calculate_rolling_drawdown,
    calculate_rolling_pnl,
    calculate_rolling_sharpe,
    calculate_rolling_win_rate,
    calculate_trade_distribution,
    calculate_yearly_returns,
)


def _eq_curve(values, dates=None):
    """Helper to build equity curve dicts."""
    if dates is None:
        dates = [f"2024-01-{i+1:02d}" for i in range(len(values))]
    return [
        {"date": d, "value": v, "close": v, "position": 0}
        for d, v in zip(dates, values)
    ]


def _trades(pnls, exit_dates):
    """Helper to build trade dicts."""
    return [
        {
            "pnl": p,
            "exit_date": d,
            "duration_bars": 5,
            "entry_price": 100,
            "exit_price": 100 + p,
        }
        for p, d in zip(pnls, exit_dates)
    ]


class TestRollingSharpe:
    def test_empty_returns_nones(self):
        """Empty equity returns all Nones."""
        result = calculate_rolling_sharpe([], window=5)
        assert result == []

    def test_insufficient_bars_returns_nones(self):
        """Less than window bars leaves all Nones."""
        result = calculate_rolling_sharpe([100, 101], window=60)
        assert len(result) == 2
        assert all(v is None for v in result)

    def test_flat_equity_gives_zero(self):
        """Flat equity (no returns) gives zero Sharpe."""
        values = [100.0] * 65
        result = calculate_rolling_sharpe(values, window=60)
        assert result[61] == 0.0
        assert result[64] == 0.0

    def test_rising_equity_positive_sharpe(self):
        """Monotonically rising equity gives positive rolling Sharpe."""
        values = [100.0 + i * 0.5 for i in range(100)]
        result = calculate_rolling_sharpe(values, window=60)
        # After enough data, rising returns should give positive Sharpe
        sharpe_values = [v for v in result[61:] if v is not None]
        assert all(s > 0 for s in sharpe_values)

    def test_volatile_equity_lower_sharpe(self):
        """Higher volatility lowers the rolling Sharpe."""
        steady = [100.0 + i * 0.1 for i in range(100)]
        volatile = [100.0 + i * 0.1 + (-1) ** i * 10 for i in range(100)]
        steady_s = calculate_rolling_sharpe(steady, window=60)
        volatile_s = calculate_rolling_sharpe(volatile, window=60)
        assert steady_s[-1] > volatile_s[-1]


class TestRollingWinRate:
    def test_empty_trades_returns_nones(self):
        """No trades produces all Nones."""
        curve = _eq_curve([100] * 10)
        result = calculate_rolling_win_rate([], curve, window=5)
        assert all(v is None for v in result)

    def test_matching_dates_counts_trades(self):
        """Trades with exit dates in window are counted."""
        values = [100] * 70
        curve = _eq_curve(values)
        trades = _trades([10, -5, 8, -3, 6], ["2024-01-65"] * 5)
        result = calculate_rolling_win_rate(trades, curve, window=5)
        # At bar 65, all 5 trades exit, 3 are wins
        assert result[65] == pytest.approx(0.6)


class TestRollingDrawdown:
    def test_flat_no_drawdown(self):
        """Flat equity has drawdown of 0."""
        result = calculate_rolling_drawdown([100] * 10)
        assert all(d == 0.0 for d in result)

    def test_dip_shows_drawdown(self):
        """A dip from peak shows negative drawdown."""
        result = calculate_rolling_drawdown([100, 90, 95, 110])
        assert result[1] == pytest.approx(-0.1)
        assert result[3] == pytest.approx(0.0)  # new peak

    def test_deep_drawdown_tracks_correctly(self):
        result = calculate_rolling_drawdown([100, 80, 85, 70])
        assert result[1] == pytest.approx(-0.2)
        assert result[3] == pytest.approx(-0.3)


class TestRollingPnl:
    def test_no_change_gives_zero(self):
        result = calculate_rolling_pnl([100, 100, 100])
        assert result[0] is None
        assert result[1] == 0.0

    def test_positive_return_calculates_pnl(self):
        result = calculate_rolling_pnl([100, 110, 105])
        assert result[1] == pytest.approx(10.0)
        assert result[2] == pytest.approx(-5.0)


class TestMonthlyReturns:
    def test_empty_returns_empty(self):
        assert calculate_monthly_returns([]) == {}

    def test_single_month(self):
        curve = _eq_curve([100, 105], ["2024-06-01", "2024-06-30"])
        result = calculate_monthly_returns(curve)
        assert result["2024-06"] == pytest.approx(0.05)

    def test_two_months(self):
        curve = _eq_curve(
            [100, 105, 110, 115],
            ["2024-06-01", "2024-06-15", "2024-07-01", "2024-07-15"],
        )
        result = calculate_monthly_returns(curve)
        assert "2024-06" in result
        assert "2024-07" in result
        assert result["2024-06"] == pytest.approx(0.05)  # 100→105


class TestYearlyReturns:
    def test_single_year(self):
        curve = _eq_curve(
            [100, 110, 120],
            ["2024-01-01", "2024-01-15", "2024-01-31"],
        )
        result = calculate_yearly_returns(curve)
        assert "2024" in result
        assert result["2024"] == pytest.approx(0.2)

    def test_multiple_years(self):
        curve = _eq_curve(
            [100, 105, 110, 115, 120, 125],
            [
                "2024-01-01",
                "2024-01-15",
                "2024-12-01",
                "2024-12-15",
                "2025-01-01",
                "2025-06-01",
            ],
        )
        result = calculate_yearly_returns(curve)
        assert "2024" in result
        assert "2025" in result


class TestExposure:
    def test_flat_position_zero_exposure(self):
        curve = _eq_curve([100] * 5)
        result = calculate_exposure(curve)
        assert all(e == 0.0 for e in result)


class TestTradeDistribution:
    def test_empty_trades(self):
        result = calculate_trade_distribution([])
        assert result["avg_pnl"] == 0.0
        assert result["pnl_bins"] == []
        assert result["pnl_percentiles"] == {}

    def test_single_trade(self):
        trades = _trades([50], ["2024-01-05"])
        result = calculate_trade_distribution(trades)
        assert result["avg_pnl"] == 50.0
        assert result["pnl_percentiles"]["p50"] == 50.0

    def test_percentiles(self):
        trades = _trades(
            [10, 20, 50, 80, 200],
            ["2024-01-01"] * 5,
        )
        result = calculate_trade_distribution(trades)
        assert result["pnl_percentiles"]["p25"] == 20.0
        assert result["pnl_percentiles"]["p50"] == 50.0
        assert result["pnl_percentiles"]["p75"] == 80.0
