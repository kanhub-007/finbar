"""ApplyIndicatorsResult DTO — output from the apply indicators use case."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ApplyIndicatorsResult:
    """Result of applying technical indicators to bars.

    bars: enriched bars with original columns plus indicator columns.
    indicators_applied: list of indicator names that were computed.
    bar_count: number of bars in the result.
    error: optional error message if computation failed.
    """

    bars: list[dict] = field(default_factory=list)
    """Enriched OHLCV bars — original keys plus indicator columns."""

    indicators_applied: list[str] = field(default_factory=list)
    """Indicator names that were successfully computed."""

    bar_count: int = 0
    """Number of bars in the result."""

    error: str | None = None
    """Error message if the operation failed."""
