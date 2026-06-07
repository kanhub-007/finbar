"""Request DTO for backtesting an unsaved JSON strategy."""

from dataclasses import dataclass, field
from typing import Any

from finbar.core.domain.entities.execution_config import ExecutionConfig

InformativeBars = list[dict] | dict[str, list[dict]]
InformativeArtifactIds = dict[str, str]


@dataclass(frozen=True)
class BacktestStrategyDefinitionRequest:
    """Input for backtesting an enriched bar set with a JSON strategy."""

    definition: str | dict
    """Strategy JSON string or parsed dictionary."""

    bars: list[dict] = field(default_factory=list)
    """Already-enriched primary OHLCV bars supplied by the agent."""

    bars_artifact_id: str = ""
    """Completed indicator job ID containing primary bars."""

    informative_bars: InformativeBars | None = None
    """Already-enriched informative OHLCV bars, if the strategy declares one."""

    informative_bars_artifact_ids: InformativeArtifactIds = field(default_factory=dict)
    """Completed indicator job IDs keyed by informative timeframe alias."""

    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    """Execution settings for this backtest run."""

    symbol: str = ""
    """Ticker symbol for result metadata."""

    interval: str = ""
    """Bar interval for result metadata."""

    initial_cash: float = 10000.0
    """Starting capital for the backtest."""

    risk_per_trade: float = 0.02
    """Fraction of portfolio to risk per trade (0.0-1.0). Default 2%."""

    params: dict[str, Any] = field(default_factory=dict)
    """Runtime strategy parameter overrides."""
