"""Structured backtest results."""

from pydantic import BaseModel


class BacktestResponse(BaseModel):
    strategy_name: str
    symbol: str
    interval: str
    start_date: str
    end_date: str
    bar_count: int
    initial_cash: float
    final_value: float
    total_return: float
    annualized_return: float | None = None
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float | None = None
    calmar_ratio: float
    trades: list[dict]
    equity_curve: list[dict]
