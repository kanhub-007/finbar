"""Result DTO for backtesting an unsaved JSON strategy."""

from dataclasses import dataclass, field

from finbar.core.application.dto.backtest_result import BacktestResultDTO
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)


@dataclass(frozen=True)
class BacktestStrategyDefinitionResult:
    """Backtest output plus validation/compilation metadata."""

    valid: bool
    """True when validation passed and the backtest was attempted."""

    result: BacktestResultDTO | None = None
    """Normal backtest result when execution succeeds."""

    errors: list[StrategyValidationError] = field(default_factory=list)
    """Validation or missing-column diagnostics."""

    required_indicators: list[str] = field(default_factory=list)
    """Concrete indicator columns required by the strategy."""

    missing_columns: list[str] = field(default_factory=list)
    """Required columns absent from the supplied enriched bars."""
