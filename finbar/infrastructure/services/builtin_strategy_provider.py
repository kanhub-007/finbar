"""BuiltinStrategyProvider — built-in strategies (none — use JSON SDK)."""

from collections.abc import Callable

from finbar_strategy_runtime.domain.entities.strategy_meta import StrategyMeta
from finbar_strategy_runtime.domain.interfaces.trading_strategy import TradingStrategy

from finbar.core.domain.interfaces.strategy_provider import StrategyProvider


class BuiltinStrategyProvider(StrategyProvider):
    """No built-in strategies — all strategies are defined via JSON SDK."""

    def __init__(self) -> None:
        self._constructors: dict[str, Callable[..., TradingStrategy]] = {}

    def create(self, name: str, params: dict | None = None) -> TradingStrategy | None:
        return None

    def list_metadata(self) -> list[StrategyMeta]:
        return []

    def exists(self, name: str) -> bool:
        return False
