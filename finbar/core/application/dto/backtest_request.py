"""BacktestRequest DTO — input for the run backtest use case."""

from dataclasses import dataclass, field

from finbar.core.domain.entities.execution_config import ExecutionConfig


@dataclass(frozen=True)
class BacktestRequest:
    """Request to run a backtest with a named strategy against historical bars.

    bars: list of OHLCV dicts (optionally enriched with indicators).
    strategy_name: name of the strategy to run (e.g. "sma_crossover").
    execution: ExecutionConfig for costs, leverage, sizing, and risk.
    params: dict of strategy parameters (e.g. {"fast_period": 20}).
    initial_cash: starting capital for the backtest.
    """

    bars: list[dict]
    """OHLCV bars. Each dict must have: open, high, low, close, volume.
    May also include indicator columns from apply_indicators."""

    strategy_name: str
    """Strategy identifier, e.g. "sma_crossover", "rsi_mean_reversion"."""

    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    """Execution settings for this backtest run."""

    symbol: str = ""
    """Ticker symbol being backtested."""

    interval: str = ""
    """Bar interval (e.g. "1d", "1h", "5min")."""

    params: dict = field(default_factory=dict)
    """Strategy parameters forwarded to the strategy."""

    initial_cash: float = 10000.0
    """Starting capital."""
