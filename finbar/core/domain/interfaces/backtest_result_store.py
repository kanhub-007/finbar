"""BacktestResultStore interface for server-side backtest results."""

from abc import ABC, abstractmethod
from typing import Any


class BacktestResultStore(ABC):
    """Store full backtest results for compact MCP access patterns."""

    @abstractmethod
    def save(self, result: dict[str, Any]) -> str:
        """Persist a full backtest result and return a result ID."""
        ...

    @abstractmethod
    def get(self, result_id: str) -> dict[str, Any] | None:
        """Return a full backtest result by ID."""
        ...

    @abstractmethod
    def list_results(
        self,
        symbol: str | None = None,
        strategy_name: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return stored result metadata records."""
        ...
