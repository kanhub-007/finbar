"""Tests for backtest performance metrics — pure math, no I/O."""


from finbar.core.domain.services.backtest_metrics import (
    calculate_annualised_return,
    calculate_calmar_ratio,
    calculate_daily_returns,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe,
    calculate_sortino,
    calculate_total_return,
    calculate_win_rate,
)


class TestSharpe:
    def test_zero_on_insufficient_data(self):
        assert calculate_sharpe([]) == 0.0
        assert calculate_sharpe([0.01]) == 0.0

    def test_positive_sharpe(self):
        # Varied upward drift: 0.1% per day with some noise
        returns = [0.001 + (i % 5) * 0.0002 for i in range(252)]
        result = calculate_sharpe(returns)
        assert result > 1.0

    def test_zero_on_zero_variance(self):
        returns = [0.0] * 252
        assert calculate_sharpe(returns) == 0.0

    def test_negative_sharpe(self):
        returns = [-0.001 - (i % 3) * 0.0001 for i in range(252)]
        assert calculate_sharpe(returns) < 0


class TestSortino:
    def test_zero_on_insufficient_data(self):
        assert calculate_sortino([]) == 0.0
        assert calculate_sortino([0.01]) == 0.0

    def test_zero_with_no_downside(self):
        returns = [0.001, 0.002, 0.001]
        assert calculate_sortino(returns) == 0.0


class TestMaxDrawdown:
    def test_zero_with_one_value(self):
        assert calculate_max_drawdown([100]) == 0.0

    def test_simple_drawdown(self):
        equity = [100, 90, 95, 85, 100]
        result = calculate_max_drawdown(equity)
        assert abs(result - 0.15) < 0.01  # (100-85)/100

    def test_no_drawdown(self):
        equity = [100, 105, 110, 115]
        assert calculate_max_drawdown(equity) == 0.0


class TestProfitFactor:
    def test_inf_with_no_losses(self):
        assert calculate_profit_factor(100, 0) == float("inf")

    def test_zero_with_no_profits(self):
        assert calculate_profit_factor(0, 100) == 0.0

    def test_ratio(self):
        assert calculate_profit_factor(200, 100) == 2.0


class TestCalmarRatio:
    def test_zero_with_no_drawdown(self):
        assert calculate_calmar_ratio(0.15, 0.0) == 0.0

    def test_ratio(self):
        assert calculate_calmar_ratio(0.30, 0.15) == 2.0


class TestWinRate:
    def test_zero_with_no_trades(self):
        assert calculate_win_rate(5, 0) == 0.0

    def test_rate(self):
        assert calculate_win_rate(6, 10) == 0.6


class TestTotalReturn:
    def test_zero_with_negative_initial(self):
        assert calculate_total_return(-100, 200) == 0.0

    def test_positive_return(self):
        assert calculate_total_return(100, 115) == 0.15

    def test_negative_return(self):
        assert calculate_total_return(100, 85) == -0.15


class TestAnnualisedReturn:
    def test_zero_with_no_days(self):
        assert calculate_annualised_return(0.15, 0) == 0.0

    def test_annualised(self):
        result = calculate_annualised_return(0.15, 252)  # exactly 1 year
        assert abs(result - 0.15) < 0.01


class TestDailyReturns:
    def test_empty_with_insufficient_data(self):
        assert calculate_daily_returns([]) == []
        assert calculate_daily_returns([100]) == []

    def test_returns(self):
        equity = [100, 110, 99]
        result = calculate_daily_returns(equity)
        assert len(result) == 2
        assert abs(result[0] - 0.1) < 0.001
        assert abs(result[1] - (-0.1)) < 0.001
