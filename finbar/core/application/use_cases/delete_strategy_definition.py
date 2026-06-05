"""DeleteStrategyDefinitionUseCase — delete a persisted strategy document."""

import logging

from finbar.core.application.dto.delete_strategy_definition_request import (
    DeleteStrategyDefinitionRequest,
)
from finbar.core.application.dto.delete_strategy_definition_result import (
    DeleteStrategyDefinitionResult,
)
from finbar.core.domain.interfaces.strategy_document_repository import (
    StrategyDocumentRepository,
)

logger = logging.getLogger(__name__)


class DeleteStrategyDefinitionUseCase:
    """Delete a JSON strategy document by name."""

    def __init__(self, repository: StrategyDocumentRepository):
        """Create the use case with a document repository.

        Args:
            repository: StrategyDocumentRepository for persistence.
        """
        self._repository = repository

    def execute(
        self, request: DeleteStrategyDefinitionRequest
    ) -> DeleteStrategyDefinitionResult:
        """Delete a strategy document.

        Args:
            request: DeleteStrategyDefinitionRequest with the strategy name.

        Returns:
            DeleteStrategyDefinitionResult indicating success or failure.
        """
        name = request.name.strip()
        if not name:
            return DeleteStrategyDefinitionResult(
                deleted=False, name="", error="Name is required"
            )

        try:
            deleted = self._repository.delete(name)
        except Exception as exc:
            logger.exception("Failed to delete strategy document '%s'", name)
            return DeleteStrategyDefinitionResult(
                deleted=False, name=name, error=str(exc)
            )

        if deleted:
            logger.info("Deleted strategy document '%s'", name)
        return DeleteStrategyDefinitionResult(deleted=deleted, name=name)
