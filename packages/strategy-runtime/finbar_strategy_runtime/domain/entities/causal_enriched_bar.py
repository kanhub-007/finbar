"""CausalEnrichedBar — immutable latest-row snapshot from streaming MTF enrichment.

A pure value object: the fully enriched primary bar (OHLCV + primary
indicators + merged informative indicators) computed using only bars
available at that primary bar's close.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CausalEnrichedBar:
    """Immutable snapshot of the latest causal enriched primary bar.

    Carries the merged row as a plain dict suitable for
    ``JsonRuleBasedStrategy.on_bar()``, the primary bar's close timestamp,
    and a readiness flag.
    """

    values: dict[str, Any] = field(default_factory=dict)
    """Merged row: OHLCV + primary indicators + suffixed informative columns."""

    timestamp: Any = None
    """Primary bar close timestamp (parseable)."""

    is_ready: bool = False
    """True once the underlying streaming indicator engine is past warmup."""
