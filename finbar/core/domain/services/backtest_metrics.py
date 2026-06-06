"""Backtest performance metrics — pure functions.

All metric calculations live here. No state, no I/O, no framework
dependencies. Used by the backtest engine to compute Sharpe, Sortino,
drawdown, and other performance ratios.
"""

import math
from collections.abc import Sequence

TRADING_DAYS_PER_YEAR = 252


def calculate_sharpe(
    daily_returns: Sequence[float],
    risk_free_rate: float = 0.0,
    annualization_factor: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualised Sharpe ratio from periodic returns.

    Args:
        daily_returns: Sequence of periodic returns as decimals.
        risk_free_rate: Annual risk-free rate (default 0).
        annualization_factor: Number of periods per year for the bar interval.

    Returns:
        Annualised Sharpe ratio.
    """
    n = len(daily_returns)
    if n < 2:
        return 0.0

    mean_all = sum(daily_returns) / n
    mean_ret = mean_all - risk_free_rate
    variance = sum((r - mean_all) ** 2 for r in daily_returns) / (n - 1)
    std_ret = math.sqrt(variance) if variance > 0 else 0.0

    if std_ret < 1e-12:
        return 0.0
    return (mean_ret / std_ret) * math.sqrt(annualization_factor)


def calculate_sortino(
    daily_returns: Sequence[float],
    risk_free_rate: float = 0.0,
    annualization_factor: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualised Sortino ratio (downside deviation only).

    Args:
        daily_returns: Sequence of periodic returns as decimals.
        risk_free_rate: Annual risk-free rate (default 0).
        annualization_factor: Number of periods per year for the bar interval.

    Returns:
        Annualised Sortino ratio.
    """
    n = len(daily_returns)
    if n < 2:
        return 0.0

    mean_ret = sum(daily_returns) / n - risk_free_rate
    downside = [r for r in daily_returns if r < 0]

    if not downside:
        return 0.0

    downside_var = sum(r**2 for r in downside) / len(downside)
    downside_std = math.sqrt(downside_var) if downside_var > 0 else 0.0

    if downside_std == 0:
        return 0.0
    return (mean_ret / downside_std) * math.sqrt(annualization_factor)


def calculate_max_drawdown(equity_values: Sequence[float]) -> float:
    """Maximum peak-to-trough drawdown as a fraction (0–1).

    Args:
        equity_values: Sequence of portfolio values over time.

    Returns:
        Maximum drawdown as a decimal (e.g. 0.15 for 15%).
    """
    if len(equity_values) < 2:
        return 0.0

    peak = equity_values[0]
    max_dd = 0.0
    for value in equity_values:
        if value > peak:
            peak = value
        dd = (peak - value) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def calculate_profit_factor(gross_profit: float, gross_loss: float) -> float:
    """Ratio of gross profit to gross loss.

    Args:
        gross_profit: Sum of all winning trade PnLs.
        gross_loss: Absolute sum of all losing trade PnLs.

    Returns:
        Profit factor. Returns infinity if gross_loss is 0.
    """
    if gross_loss <= 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def calculate_calmar_ratio(
    annualised_return: float,
    max_drawdown: float,
) -> float:
    """Calmar ratio: annualised return / max drawdown.

    Args:
        annualised_return: Annualised return as a decimal.
        max_drawdown: Maximum drawdown as a decimal.

    Returns:
        Calmar ratio. Returns 0.0 if max_drawdown is 0.
    """
    if max_drawdown <= 0:
        return 0.0
    return annualised_return / max_drawdown


def calculate_win_rate(winning: int, total: int) -> float:
    """Simple win rate.

    Args:
        winning: Number of winning trades.
        total: Total number of trades.

    Returns:
        Win rate as a decimal.
    """
    if total <= 0:
        return 0.0
    return winning / total


def calculate_total_return(initial: float, final: float) -> float:
    """Total return as a fraction.

    Args:
        initial: Starting portfolio value.
        final: Ending portfolio value.

    Returns:
        Total return as a decimal.
    """
    if initial <= 0:
        return 0.0
    return (final - initial) / initial


def calculate_annualised_return(
    total_return: float,
    trading_days: int,
    annualization_factor: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualise a total return.

    Args:
        total_return: Total return as a decimal.
        trading_days: Number of periods in the backtest.
        annualization_factor: Number of periods per year for the bar interval.

    Returns:
        Annualised return as a decimal.
    """
    if trading_days <= 0 or annualization_factor <= 0:
        return 0.0
    years = trading_days / annualization_factor
    if years <= 0:
        return 0.0
    return (1 + total_return) ** (1 / years) - 1


def calculate_daily_returns(equity_values: Sequence[float]) -> list[float]:
    """Convert equity curve to daily returns.

    Args:
        equity_values: Sequence of portfolio values over time.

    Returns:
        List of daily returns as decimals.
    """
    if len(equity_values) < 2:
        return []
    return [
        (
            (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
            if equity_values[i - 1] > 0
            else 0.0
        )
        for i in range(1, len(equity_values))
    ]
