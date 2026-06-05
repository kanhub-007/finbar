"""IndicatorJob entity for asynchronous indicator computation."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class IndicatorJob:
    """Background indicator job state for indicator/feature calculation."""

    job_id: str
    """Unique job identifier."""

    status: str = "queued"
    """Job status: queued, running, completed, failed, or cancelled."""

    symbol: str = ""
    """Symbol being enriched."""

    source: str = ""
    """Data source, e.g. yfinance or hyperliquid."""

    interval: str = ""
    """Primary interval being enriched."""

    mode: str = "selected"
    """Computation mode: selected or strategy_required."""

    timeframe_alias: str = "primary"
    """Strategy timeframe alias represented by this job."""

    start_date: str | None = None
    """Optional start-date filter used for cached bars."""

    end_date: str | None = None
    """Optional end-date filter used for cached bars."""

    progress_pct: int = 0
    """Progress percentage from 0 to 100."""

    stage: str = "queued"
    """Current job stage for agent progress messages."""

    message: str = ""
    """Human-readable progress message."""

    total_bar_count: int = 0
    """Total enriched bars available when completed."""

    indicators_applied: list[str] = field(default_factory=list)
    """Indicators applied by the job."""

    features_applied: list[str] = field(default_factory=list)
    """Features applied by the job."""

    error: str | None = None
    """Error message for failed jobs."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional machine-readable job metadata."""

    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    """Creation timestamp used for cleanup."""
