"""SaveStrategyDefinitionUseCase — validate then persist a strategy document."""

import json
import logging
from datetime import UTC, datetime

import yaml

from finbar.core.application.dto.save_strategy_definition_request import (
    SaveStrategyDefinitionRequest,
)
from finbar.core.application.dto.save_strategy_definition_result import (
    SaveStrategyDefinitionResult,
)
from finbar.core.domain.entities.strategy_document import StrategyDocument
from finbar.core.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.domain.interfaces.strategy_document_repository import (
    StrategyDocumentRepository,
)

logger = logging.getLogger(__name__)


class SaveStrategyDefinitionUseCase:
    """Validate a JSON strategy definition and persist it if valid."""

    def __init__(
        self,
        repository: StrategyDocumentRepository,
        parser: StrategyDefinitionParser | None = None,
    ):
        """Create the use case with a document repository and optional parser.

        Args:
            repository: StrategyDocumentRepository for persistence.
            parser: Optional parser; defaults to concrete implementation.
        """
        self._repository = repository

        if parser is not None:
            self._parser = parser
        else:
            from finbar.core.application.services.strategy_definition_parser import (
                StrategyDefinitionParser as ConcreteParser,
            )

            self._parser = ConcreteParser()

    def execute(
        self, request: SaveStrategyDefinitionRequest
    ) -> SaveStrategyDefinitionResult:
        """Validate and save a strategy definition.

        Args:
            request: SaveStrategyDefinitionRequest with the JSON definition.

        Returns:
            SaveStrategyDefinitionResult indicating success or structured errors.
        """
        try:
            raw = json.loads(request.definition_json)
        except json.JSONDecodeError:
            try:
                raw = yaml.safe_load(request.definition_json)
                if not isinstance(raw, dict):
                    return SaveStrategyDefinitionResult(
                        saved=False, error="Definition must be a JSON or YAML object"
                    )
            except yaml.YAMLError as exc:
                return SaveStrategyDefinitionResult(
                    saved=False, error=f"Invalid JSON or YAML: {exc}"
                )

        validation = self._parser.parse(raw)

        if not validation.valid:
            return SaveStrategyDefinitionResult(
                saved=False,
                validation_errors=validation.errors,
                error="Validation failed — see validation_errors for details",
            )

        if validation.definition is None:
            return SaveStrategyDefinitionResult(
                saved=False,
                error="Parsed definition is None despite passing validation",
            )

        name = request.name_override or validation.definition.name
        if not name:
            return SaveStrategyDefinitionResult(
                saved=False, error="Strategy name is required"
            )

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        normalized = json.dumps(validation.normalized, indent=2, sort_keys=True)

        document = StrategyDocument(
            name=name,
            schema_version=validation.definition.schema_version,
            description=validation.definition.description,
            definition_json=request.definition_json,
            normalized_json=normalized,
            created_at=now,
            updated_at=now,
        )

        try:
            self._repository.save(document)
        except Exception as exc:
            logger.exception("Failed to save strategy document '%s'", name)
            return SaveStrategyDefinitionResult(
                saved=False,
                name=name,
                error=f"Database error: {exc}",
            )

        logger.info("Saved strategy document '%s' (v%s)", name, document.schema_version)
        return SaveStrategyDefinitionResult(
            saved=True,
            name=name,
            schema_version=document.schema_version,
        )
