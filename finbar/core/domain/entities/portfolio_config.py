"""PortfolioConfig — configuration for multi-asset portfolio backtesting.

Pure dataclass — no behavior, no ORM, no framework dependencies.
"""

from dataclasses import dataclass, field

from finbar.core.domain.entities.execution_config import ExecutionConfig


@dataclass(frozen=True)
class AssetAllocation:
    """Single asset in a portfolio with its strategy and allocation weight.

    Attributes:
        symbol: Ticker symbol.
        strategy_name: Name of a built-in or saved strategy, or empty
            to use the definition dict.
        weight: Relative capital allocation (e.g. 1.0 = equal weight).
            Normalized across all assets in the portfolio.
        max_position_size: Per-asset maximum position size. 0 = no limit.
        bars: OHLCV bars for this asset (provided at runtime, not persisted).
    """

    symbol: str = ""
    strategy_name: str = ""
    weight: float = 1.0
    max_position_size: float = 0.0
    bars: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class PortfolioConfig:
    """Configuration for a multi-asset portfolio backtest.

    Attributes:
        assets: One entry per asset, each with symbol, strategy, weight.
        execution: Shared execution settings for all strategies.
        max_positions: Maximum concurrent open positions across all assets.
            Default 10 (effectively unlimited for most portfolios).
        max_exposure_pct: Maximum fraction of total equity that can be
            deployed in positions at any time. 1.0 = 100%.
    """

    assets: list[AssetAllocation] = field(default_factory=list)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    max_positions: int = 10
    max_exposure_pct: float = 1.0
