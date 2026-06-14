"""ValidateStrategyDefinitionUseCase — validate strategy JSON."""

from finbar_strategy_runtime.domain.entities.strategy_validation_result import (
    StrategyValidationResult,
)
from finbar_strategy_runtime.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser,
)


class ValidateStrategyDefinitionUseCase:
    """Validate and normalize an agent-authored strategy definition."""

    def __init__(self, parser: StrategyDefinitionParser):
        """Create the use case with an injectable parser."""
        self._parser = parser

    def execute(
        self,
        definition: str | dict,
        params: dict | None = None,
    ) -> StrategyValidationResult:
        """Validate a JSON strategy definition and return diagnostics."""
        return self._parser.parse(definition, params or {})
