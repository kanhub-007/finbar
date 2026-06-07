"""ComputeStrategyIndicatorsResult — multi-timeframe indicator job DTO."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ComputeStrategyIndicatorsResult:
    """Result containing indicator job IDs for each required timeframe."""

    strategy_name: str = ""
    """Strategy name from the definition."""

    valid: bool = False
    """True when validation passed and jobs were started."""

    primary: dict[str, Any] = field(default_factory=dict)
    """Primary timeframe job metadata."""

    informative: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Informative timeframe alias → job metadata."""

    primary_required_indicators: list[str] = field(default_factory=list)
    """Required indicators for the primary timeframe."""

    informative_required_indicators: dict[str, list[str]] = field(default_factory=dict)
    """Required indicators by informative timeframe alias."""

    errors: list[dict[str, str]] = field(default_factory=list)
    """Validation errors."""

    error: str | None = None
    """Error message if the computation failed."""
