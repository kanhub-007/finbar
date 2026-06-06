"""DerivativesRepository — domain interface for derivatives metrics persistence.

Repository pattern: application use cases depend on this ABC, never on
concrete infrastructure (SqlCoinGlassRepository).
"""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.derivatives_metrics import DerivativesMetrics


class DerivativesRepository(ABC):
    """Abstract repository for derivatives market metrics."""

    @abstractmethod
    def save(self, metrics: DerivativesMetrics) -> None:
        """Persist a single derivatives metrics record."""
        ...

    @abstractmethod
    def save_batch(self, metrics_list: list[DerivativesMetrics]) -> None:
        """Persist a batch of derivatives metrics records."""
        ...

    @abstractmethod
    def find(
        self,
        symbol: str,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[DerivativesMetrics]:
        """Query derivatives metrics for a symbol with optional time range."""
        ...

    @abstractmethod
    def latest(self, symbol: str) -> DerivativesMetrics | None:
        """Return the most recent derivatives metrics for a symbol."""
        ...
