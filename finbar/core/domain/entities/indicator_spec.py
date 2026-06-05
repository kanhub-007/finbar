"""IndicatorSpec entity for JSON strategies."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IndicatorSpec:
    """A strategy-local indicator alias and its concrete computed column.

    Agents can reference aliases such as ``fast_sma`` in rules. Validation
    resolves those aliases to concrete enrichment columns such as ``sma_20``.
    """

    name: str
    """Strategy-local alias used by conditions."""

    type: str
    """Indicator type, e.g. sma, ema, rsi, atr, or rvol."""

    concrete_name: str
    """Concrete column expected to already exist on enriched bars."""

    period: int | None = None
    """Resolved period for period-based indicators."""

    source: str = "close"
    """Input source column used by the enrichment layer."""

    raw_period: Any = None
    """Original period expression from JSON before parameter resolution."""
