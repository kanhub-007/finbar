"""Request DTO for applying v2 strategy derived features."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ApplyStrategyFeaturesRequest:
    """Input for calculating features declared by a v2 strategy JSON document."""

    definition: str | dict
    """Strategy JSON string or parsed dictionary."""

    bars: list[dict]
    """Already price/indicator-enriched bars supplied by the agent."""

    params: dict[str, Any] = field(default_factory=dict)
    """Runtime strategy parameter overrides."""
