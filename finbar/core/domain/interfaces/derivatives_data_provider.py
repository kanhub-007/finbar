"""DerivativesDataProvider — domain interface for derivatives market data.

Provider‑agnostic — any data source (CoinGlass, Velo, Laevitas) can
implement this ABC.
"""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.derivatives_metrics import DerivativesMetrics


class DerivativesDataProvider(ABC):
    """Fetch derivatives market metrics for a symbol and time range.

    Implementations handle API authentication, rate limiting, and
    data normalisation — the domain layer only depends on this
    abstract interface.
    """

    @abstractmethod
    def fetch(
        self,
        symbol: str,
        interval: str = "1h",
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[DerivativesMetrics]:
        """Fetch derivatives metrics for a symbol.

        Args:
            symbol: Ticker symbol (e.g. "BTC").
            interval: Bar interval for the data (e.g. "1h", "4h", "1d").
            start_time: ISO‑8601 start of the time range (inclusive).
            end_time: ISO‑8601 end of the time range (exclusive).

        Returns:
            List of DerivativesMetrics, one per time point.

        Raises:
            ValueError: If the symbol is not supported by this provider.
            RuntimeError: On network or authentication errors.
        """
        ...
