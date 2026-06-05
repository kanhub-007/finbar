"""StrategyProvider interface — resolves trading strategies by name."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.strategy_meta import StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy


class StrategyProvider(ABC):
    """Creates trading strategy instances and exposes strategy metadata."""

    @abstractmethod
    def create(self, name: str, params: dict | None = None) -> TradingStrategy | None:
        """Create a strategy instance by name.

        Args:
            name: Strategy identifier.
            params: Optional per-run parameter overrides.

        Returns:
            A new TradingStrategy instance, or None when unknown.
        """
        ...

    @abstractmethod
    def list_metadata(self) -> list[StrategyMeta]:
        """List metadata for available strategies."""
        ...

    @abstractmethod
    def exists(self, name: str) -> bool:
        """Return True if the provider can create the named strategy."""
        ...
