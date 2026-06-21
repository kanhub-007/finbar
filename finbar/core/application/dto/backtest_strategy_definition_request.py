"""Request DTO for backtesting an unsaved JSON strategy."""

from dataclasses import dataclass, field
from typing import Any, Literal

from finbar.core.domain.entities.execution_config import ExecutionConfig

InformativeBars = list[dict] | dict[str, list[dict]]
InformativeArtifactIds = dict[str, str]

EnrichmentMode = Literal["batch_full_frame", "live_parity_streaming"]


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

    enrichment_mode: EnrichmentMode = "live_parity_streaming"
    """Enrichment data horizon. Defaults to the realistic (causal) mode so
    backtest results reproduce what would actually occur in live trading.

    - ``live_parity_streaming`` (default): each bar's enriched row is built
      from the causal ``CausalMultiTimeframeStreamingEnricher`` using only
      bars available at that bar's close. Required oracle for live-tradable
      strategies and Finbot parity.
    - ``batch_full_frame``: legacy full-frame batch enrichment. NOT
      live-parity safe for frame-dependent indicators (session VP/AMT);
      kept for research/repro only and flagged in result metadata.
    """
