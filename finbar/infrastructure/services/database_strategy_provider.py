"""Provider that resolves saved strategy documents into executable strategies."""

import json

from finbar.core.domain.entities.strategy_kind import StrategyKind
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.domain.interfaces.strategy_document_repository import (
    StrategyDocumentRepository,
)
from finbar.core.domain.interfaces.strategy_provider import StrategyProvider
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.strategy_definition_factory import (
    StrategyDefinitionFactory,
)


def _flat_indicators(definition: dict) -> list[str]:
    indicators: list[str] = []
    seen: set[str] = set()
    for indicator in definition.get("indicators", []):
        name = indicator.get("concrete_name", indicator.get("name", ""))
        if name and name not in seen:
            indicators.append(name)
            seen.add(name)
    risk = definition.get("risk", {})
    for section in [risk.get("stop_loss", {}), risk.get("take_profit", {})]:
        if section.get("type") == "atr" and "atr" not in seen:
            indicators.append("atr")
            seen.add("atr")
    return sorted(indicators)


def _flat_features(definition: dict) -> list[str]:
    return [f["name"] for f in definition.get("features", [])]


class DatabaseStrategyProvider(StrategyProvider):
    """Resolves saved strategy documents into executable strategies."""

    def __init__(
        self,
        repository: StrategyDocumentRepository,
        parser: StrategyDefinitionParser,
    ):
        """Initialize with a strategy document repository.

        Args:
            repository: StrategyDocumentRepository for persistence lookups.
            parser: Parser for JSON definitions (injected from composition root).
        """
        self._repository = repository
        self._factory = StrategyDefinitionFactory()
        self._parser = parser

    def create(self, name: str, params: dict | None = None) -> TradingStrategy | None:
        """Create a JsonRuleBasedStrategy from a saved document.

        Args:
            name: Strategy name.
            params: Optional parameter overrides.
        """
        document = self._repository.find_by_name(name)
        if document is None:
            return None
        validation = self._parser.parse(
            document.definition_json, param_overrides=params
        )
        if validation.definition is None:
            return None
        return self._factory.create(validation.definition)

    def list_metadata(self) -> list[StrategyMeta]:
        """List metadata for all saved strategy documents."""
        result: list[StrategyMeta] = []
        for doc in self._repository.list_all():
            try:
                definition = json.loads(doc.definition_json)
            except json.JSONDecodeError:
                continue
            result.append(
                StrategyMeta(
                    name=doc.name,
                    variant=DataMode.REAL,
                    kind=StrategyKind.USER_DEFINED,
                    description=doc.description or definition.get("description", ""),
                    required_indicators=_flat_indicators(definition),
                    required_features=_flat_features(definition),
                    params=definition.get("parameters", {}),
                )
            )
        return result

    def exists(self, name: str) -> bool:
        """Return True if a strategy document exists with this name."""
        return self._repository.find_by_name(name) is not None
