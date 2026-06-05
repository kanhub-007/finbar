"""Request DTO for backtesting an unsaved v2 JSON strategy."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BacktestStrategyDefinitionRequest:
    """Input for backtesting an already-enriched bar set with a JSON strategy."""

    definition: str | dict
    """Strategy JSON string or parsed dictionary."""

    bars: list[dict]
    """Already-enriched OHLCV bars supplied by the orchestrating agent."""

    symbol: str = ""
    """Ticker symbol for result metadata."""

    interval: str = ""
    """Bar interval for result metadata."""

    initial_cash: float = 10000.0
    """Starting capital for the backtest."""

    params: dict[str, Any] = field(default_factory=dict)
    """Runtime strategy parameter overrides."""
