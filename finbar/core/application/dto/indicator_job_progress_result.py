"""Result DTO for indicator job progress."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IndicatorJobProgressResult:
    """Current progress state for an indicator job."""

    found: bool
    """True when the job exists."""

    job_id: str = ""
    status: str = ""
    symbol: str = ""
    source: str = ""
    interval: str = ""
    mode: str = ""
    timeframe_alias: str = "primary"
    progress_pct: int = 0
    stage: str = ""
    message: str = ""
    total_bar_count: int = 0
    indicators_applied: list[str] = field(default_factory=list)
    features_applied: list[str] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
