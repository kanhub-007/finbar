"""Core domain — entities, interfaces, and pure business logic.

No database, no framework, no I/O dependencies in this layer.
"""

from finbar.core.domain.entities import DataMode, SignalResult, StrategyMeta
from finbar.core.domain.interfaces import (
    BacktestEngine,
    IndicatorCalculator,
    TradingStrategy,
)

__all__ = [
    "BacktestEngine",
    "DataMode",
    "IndicatorCalculator",
    "SignalResult",
    "StrategyMeta",
    "TradingStrategy",
]
