"""FetchDerivativesUseCase — fetch and persist derivatives market metrics."""

import logging

from finbar.core.application.dto.fetch_derivatives_request import (
    FetchDerivativesRequest,
)
from finbar.core.application.dto.fetch_derivatives_result import (
    FetchDerivativesResult,
)
from finbar.core.domain.interfaces.derivatives_data_provider import (
    DerivativesDataProvider,
)
from finbar.infrastructure.repositories.sql_coinglass_repository import (
    SqlCoinGlassRepository,
)

logger = logging.getLogger(__name__)


class FetchDerivativesUseCase:
    """Fetch derivatives metrics from a provider and persist to the database.

    Synchronous — the provider handles its own retry/backoff logic.
    """

    def __init__(
        self,
        provider: DerivativesDataProvider,
        repository: SqlCoinGlassRepository,
    ):
        """Create the use case with injected provider and repository.

        Args:
            provider: Concrete derivatives data provider (e.g. CoinGlassClient).
            repository: Repository for persisting fetched metrics.
        """
        self._provider = provider
        self._repository = repository

    def execute(
        self,
        request: FetchDerivativesRequest,
    ) -> FetchDerivativesResult:
        """Fetch and persist derivatives metrics.

        Args:
            request: Fetch parameters (symbol, interval, time range).

        Returns:
            FetchDerivativesResult with fetched metrics or error.
        """
        try:
            metrics = self._provider.fetch(
                symbol=request.symbol,
                interval=request.interval,
                start_time=request.start_time,
                end_time=request.end_time,
            )
        except Exception as exc:
            logger.exception("Failed to fetch derivatives for %s", request.symbol)
            return FetchDerivativesResult(
                symbol=request.symbol,
                interval=request.interval,
                error=str(exc),
            )

        if metrics:
            try:
                self._repository.save_batch(metrics)
            except Exception as exc:
                logger.warning(
                    "Failed to persist derivatives for %s: %s",
                    request.symbol,
                    exc,
                )
                # Return the data even if persistence fails

        return FetchDerivativesResult(
            symbol=request.symbol,
            interval=request.interval,
            metrics=metrics,
            count=len(metrics),
        )
