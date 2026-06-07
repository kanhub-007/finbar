"""RunStrategyPipelineResult — orchestrated pipeline result DTO."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunStrategyPipelineResult:
    """Result from the one-call strategy pipeline."""

    complete: bool
    """True when the full pipeline finished successfully."""

    stage: str = ""
    """Last completed pipeline stage."""

    result_id: str = ""
    """Backtest result ID when pipeline is complete."""

    response: dict[str, Any] = field(default_factory=dict)
    """Compact backtest response envelope."""

    validation: dict[str, Any] = field(default_factory=dict)
    """Strategy validation metadata."""

    indicators: dict[str, Any] = field(default_factory=dict)
    """Indicator job metadata per timeframe."""

    missing_price_data: dict[str, str] = field(default_factory=dict)
    """Intervals for which price data is missing with fetch instructions."""

    errors: list[dict[str, str]] = field(default_factory=list)
    """Diagnostic errors."""

    error: str | None = None
    """Error message if pipeline failed."""
