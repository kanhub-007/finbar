"""OptimizationResult entity for a single backtest result in a sweep."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OptimizationResult:
    """A single parameter combination and its backtest metrics."""

    rank: int
    """Position when sorted by the chosen metric (1 = best)."""

    params: dict[str, Any]
    """Parameter values for this combination."""

    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    calmar_ratio: float = 0.0
    total_trades: int = 0
    error: str | None = None
