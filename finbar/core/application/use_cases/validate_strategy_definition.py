"""ValidateStrategyDefinitionUseCase — validate strategy JSON."""

from finbar.core.application.services.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.domain.entities.strategy_validation_result import (
    StrategyValidationResult,
)


class ValidateStrategyDefinitionUseCase:
    """Validate and normalize an agent-authored strategy definition."""

    def __init__(self, parser: StrategyDefinitionParser | None = None):
        """Create the use case with an injectable parser."""
        self._parser = parser or StrategyDefinitionParser()

    def execute(
        self,
        definition: str | dict,
        params: dict | None = None,
    ) -> StrategyValidationResult:
        """Validate a JSON strategy definition and return diagnostics."""
        return self._parser.parse(definition, params or {})
