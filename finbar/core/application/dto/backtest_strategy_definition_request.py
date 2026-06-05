"""Request DTO for backtesting an unsaved JSON strategy."""

from dataclasses import dataclass, field
from typing import Any

InformativeBars = list[dict] | dict[str, list[dict]]


@dataclass(frozen=True)
class BacktestStrategyDefinitionRequest:
    """Input for backtesting an already-enriched bar set with a JSON strategy."""

    definition: str | dict
    """Strategy JSON string or parsed dictionary."""

    bars: list[dict]
    """Already-enriched primary OHLCV bars supplied by the agent."""

    informative_bars: InformativeBars | None = None
    """Already-enriched informative OHLCV bars, if the strategy declares one."""

    symbol: str = ""
    """Ticker symbol for result metadata."""

    interval: str = ""
    """Bar interval for result metadata."""

    initial_cash: float = 10000.0
    """Starting capital for the backtest."""

    params: dict[str, Any] = field(default_factory=dict)
    """Runtime strategy parameter overrides."""
