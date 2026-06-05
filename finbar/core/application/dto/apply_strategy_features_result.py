"""Result DTO for applying strategy derived features."""

from dataclasses import dataclass, field

from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)


@dataclass(frozen=True)
class ApplyStrategyFeaturesResult:
    """Output from strategy feature calculation."""

    bars: list[dict] = field(default_factory=list)
    """Bars with derived feature columns added."""

    features_applied: list[str] = field(default_factory=list)
    """Feature columns that were calculated."""

    bar_count: int = 0
    """Number of bars returned."""

    errors: list[StrategyValidationError] = field(default_factory=list)
    """Validation or calculation diagnostics."""

    error: str | None = None
    """Convenience error message for API/MCP clients."""
