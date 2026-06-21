"""MultiTimeframeStreamingEnricher — incremental causal MTF enrichment contract.

Package-level pure service. Callers feed closed informative and primary
bars in chronological order; ``update_primary()`` returns the latest
causal enriched primary bar computed only from bars available at that
primary bar's close. Both Finbar live-parity backtests and Finbot
live/replay consume the same implementation (ADR-3).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from finbar_strategy_runtime.domain.entities.causal_enriched_bar import (
    CausalEnrichedBar,
)


class MultiTimeframeStreamingEnricher(ABC):
    """Incrementally enrich primary bars with informative timeframe context.

    Callers feed closed informative and primary bars in chronological
    order. ``update_primary()`` returns the latest causal enriched
    primary bar.
    """

    @abstractmethod
    def update_informative(self, alias: str, bar: dict) -> None:
        """Ingest one closed informative bar for the given alias.

        Args:
            alias: Informative timeframe alias (e.g. ``"h1"``).
            bar: Closed OHLCV bar dict with a parseable ``timestamp``.
        """

    @abstractmethod
    def update_primary(self, bar: dict) -> CausalEnrichedBar:
        """Ingest one closed primary bar; return the latest causal enriched bar.

        Args:
            bar: Closed OHLCV bar dict with a parseable ``timestamp``.

        Returns:
            The latest merged enriched primary bar.
        """

    @abstractmethod
    def latest(self) -> CausalEnrichedBar | None:
        """Return the most recent enriched bar without ingesting a bar."""

    @abstractmethod
    def reset(self) -> None:
        """Clear all per-timeframe state."""
