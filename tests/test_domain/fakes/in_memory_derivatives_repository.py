"""In-memory fake of DerivativesRepository for testing (Classical school).

Returns whatever list was injected via the constructor — a real
implementation, not a recording mock.
"""

from finbar.core.domain.entities.derivatives_metrics import DerivativesMetrics
from finbar.core.domain.interfaces.derivatives_repository import DerivativesRepository


class InMemoryDerivativesRepository(DerivativesRepository):
    """Fake repository that stores data in memory.

    Classical school: provides real behaviour (stores and retrieves),
    not interaction recording.
    """

    def __init__(self, data: list[DerivativesMetrics] | None = None) -> None:
        self._data: list[DerivativesMetrics] = list(data) if data else []

    def save(self, metrics: DerivativesMetrics) -> None:
        """Store a single record."""
        self._data.append(metrics)

    def save_batch(self, metrics_list: list[DerivativesMetrics]) -> None:
        """Store a batch of records."""
        self._data.extend(metrics_list)

    def find(
        self,
        symbol: str,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[DerivativesMetrics]:
        """Query records for a symbol with optional time range."""
        results = [m for m in self._data if m.symbol == symbol]
        if start_time:
            results = [m for m in results if m.timestamp >= start_time]
        if end_time:
            results = [m for m in results if m.timestamp <= end_time]
        return results

    def latest(self, symbol: str) -> DerivativesMetrics | None:
        """Return the most recent record for a symbol."""
        matching = self.find(symbol)
        if not matching:
            return None
        return max(matching, key=lambda m: m.timestamp)
