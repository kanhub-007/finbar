"""BuiltinStrategyProvider — creates built-in Python trading strategies."""

from collections.abc import Callable
from typing import Any

from finbar.core.domain.entities.strategy_meta import StrategyMeta
from finbar.core.domain.interfaces.strategy_provider import StrategyProvider
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.backtest_strategies.auction_drive import (
    AuctionDriveStrategy,
)
from finbar.infrastructure.services.backtest_strategies.momentum_breakout import (
    MomentumBreakoutStrategy,
)
from finbar.infrastructure.services.backtest_strategies.rsi_mean_reversion import (
    RsiMeanReversionStrategy,
)
from finbar.infrastructure.services.backtest_strategies.sma_crossover import (
    SmaCrossoverStrategy,
)


class BuiltinStrategyProvider(StrategyProvider):
    """Creates fresh instances of built-in strategies for each backtest run."""

    def __init__(self) -> None:
        """Initialize the built-in strategy constructor registry."""
        self._constructors: dict[str, Callable[..., TradingStrategy]] = {
            "sma_crossover": SmaCrossoverStrategy,
            "rsi_mean_reversion": RsiMeanReversionStrategy,
            "momentum_breakout": MomentumBreakoutStrategy,
            "auction_drive": AuctionDriveStrategy,
        }

    def create(self, name: str, params: dict | None = None) -> TradingStrategy | None:
        """Create a fresh built-in strategy instance with parameter overrides."""
        constructor = self._constructors.get(name)
        if constructor is None:
            return None
        return constructor(**_filter_params(params or {}))

    def list_metadata(self) -> list[StrategyMeta]:
        """List metadata for all built-in strategies."""
        return [self.create(name).meta() for name in sorted(self._constructors)]

    def exists(self, name: str) -> bool:
        """Return True if ``name`` is a built-in strategy."""
        return name in self._constructors


def _filter_params(params: dict[str, Any]) -> dict[str, Any]:
    """Drop empty-string values from loosely parsed client parameters."""
    return {key: value for key, value in params.items() if value != ""}
