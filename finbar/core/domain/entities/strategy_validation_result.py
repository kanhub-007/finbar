"""StrategyValidationResult entity for v2 JSON validation."""

from dataclasses import dataclass, field

from finbar.core.domain.entities.strategy_definition_v2 import StrategyDefinitionV2
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)


@dataclass(frozen=True)
class StrategyValidationResult:
    """Structured validation result for an agent-authored strategy."""

    valid: bool
    """True when the strategy parsed and passed semantic validation."""

    errors: list[StrategyValidationError] = field(default_factory=list)
    """Path-specific validation errors."""

    warnings: list[StrategyValidationError] = field(default_factory=list)
    """Path-specific non-fatal warnings."""

    definition: StrategyDefinitionV2 | None = None
    """Canonical strategy definition when valid."""

    required_indicators: list[str] = field(default_factory=list)
    """Concrete indicator columns requested by declared indicator aliases."""

    required_columns: list[str] = field(default_factory=list)
    """Concrete bar columns required to execute the strategy."""

    missing_columns: list[str] = field(default_factory=list)
    """Required bar columns missing from a supplied enriched dataset."""

    normalized: dict = field(default_factory=dict)
    """Canonical normalized v2 JSON representation of the parsed definition."""
