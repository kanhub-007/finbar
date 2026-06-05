"""Request DTO for starting an asynchronous enrichment job."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StartEnrichmentJobRequest:
    """Input for server-side cached-price enrichment jobs."""

    symbol: str
    """Symbol to enrich from the local cache."""

    source: str = "yfinance"
    """Data source namespace used in the cache."""

    interval: str = "1d"
    """Interval to enrich from the local cache."""

    mode: str = "selected"
    """selected or strategy_required."""

    indicators: list[str] = field(default_factory=list)
    """Indicators to apply in selected mode."""

    definition: str | dict | None = None
    """Strategy definition for strategy_required mode."""

    params: dict[str, Any] = field(default_factory=dict)
    """Runtime strategy parameter overrides."""

    timeframe_alias: str = "primary"
    """Timeframe alias for strategy_required mode."""

    start_date: str | None = None
    """Optional cached price start-date filter."""

    end_date: str | None = None
    """Optional cached price end-date filter."""
