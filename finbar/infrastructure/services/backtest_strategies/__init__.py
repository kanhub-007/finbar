"""Built-in backtest strategies.

Each strategy implements the TradingStrategy(ABC) domain interface.
The on_bar() method is called once per bar by the backtest engine.
Strategies are pure trading logic — no framework dependencies.
"""

from finbar.infrastructure.services.backtest_strategies.auction_drive import (
    AuctionDriveStrategy,
)
from finbar.infrastructure.services.backtest_strategies.rsi_mean_reversion import (
    RsiMeanReversionStrategy,
)
from finbar.infrastructure.services.backtest_strategies.sma_crossover import (
    SmaCrossoverStrategy,
)

__all__ = [
    "AuctionDriveStrategy",
    "RsiMeanReversionStrategy",
    "SmaCrossoverStrategy",
]
