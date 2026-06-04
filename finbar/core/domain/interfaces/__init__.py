"""Domain interfaces — contracts for indicator calculation, trading
strategies, and backtest engines. All are abstract (ABC) — concrete
implementations live in infrastructure/services/."""

from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
from finbar.core.domain.interfaces.indicator_calculator import IndicatorCalculator
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy

__all__ = ["BacktestEngine", "IndicatorCalculator", "TradingStrategy"]
