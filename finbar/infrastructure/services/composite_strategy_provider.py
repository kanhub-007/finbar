"""CompositeStrategyProvider — resolves strategies from multiple providers."""

from finbar.core.domain.entities.strategy_meta import StrategyMeta
from finbar.core.domain.interfaces.strategy_provider import StrategyProvider
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy


class CompositeStrategyProvider(StrategyProvider):
    """Strategy provider that tries child providers in order."""

    def __init__(self, providers: list[StrategyProvider]):
        """Initialize with ordered child providers."""
        self._providers = providers

    def create(self, name: str, params: dict | None = None) -> TradingStrategy | None:
        """Create a strategy from the first provider that knows ``name``."""
        for provider in self._providers:
            strategy = provider.create(name, params)
            if strategy is not None:
                return strategy
        return None

    def list_metadata(self) -> list[StrategyMeta]:
        """List metadata from all child providers, de-duplicated by name."""
        seen: set[str] = set()
        metadata: list[StrategyMeta] = []
        for provider in self._providers:
            for meta in provider.list_metadata():
                if meta.name not in seen:
                    seen.add(meta.name)
                    metadata.append(meta)
        return sorted(metadata, key=lambda item: item.name)

    def exists(self, name: str) -> bool:
        """Return True if any child provider knows ``name``."""
        return any(provider.exists(name) for provider in self._providers)
