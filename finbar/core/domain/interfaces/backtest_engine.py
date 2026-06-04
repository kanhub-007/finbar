"""Domain interface for the backtest engine.

Template Method pattern — the engine defines a fixed skeleton:
initialise → loop bars → call strategy → execute signals → close positions
→ compute metrics. The strategy varies (Strategy pattern).
"""

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

from finbar.core.domain.interfaces.trading_strategy import TradingStrategy


class BacktestEngine(ABC):
    """Bar-by-bar backtest runner using Template Method pattern.

    The skeleton is fixed; the strategy passed to ``run()`` varies.
    Implementations handle position tracking, trade execution, and
    metric computation.
    """

    @abstractmethod
    def run(
        self,
        df: pd.DataFrame,
        strategy: TradingStrategy,
        initial_cash: float = 10000.0,
        **params: Any,
    ) -> dict:
        """Execute a backtest.

        Iterates bars in ``df``, calls ``strategy.on_bar()`` for each
        bar, executes resulting signals, and computes performance metrics.

        Args:
            df: DataFrame with OHLCV columns [open, high, low, close, volume]
                plus any indicator columns needed by the strategy.
                Index must be datetime.
            strategy: Trading strategy instance to evaluate.
            initial_cash: Starting capital (default 10,000).
            **params: Additional strategy parameters forwarded to the strategy.

        Returns:
            Dict with backtest results:
                - strategy_name: str
                - symbol: str
                - interval: str
                - start_date, end_date: str
                - bar_count: int
                - initial_cash, final_value, total_return: float
                - total_trades, winning_trades, losing_trades: int
                - win_rate, max_drawdown, sharpe_ratio, sortino_ratio: float
                - profit_factor, calmar_ratio: float
                - trades: list of trade dicts
                - equity_curve: list of equity snapshot dicts
        """
        ...
