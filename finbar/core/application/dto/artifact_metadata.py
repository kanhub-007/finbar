"""ArtifactMetadata — compact metadata for stored bar artifacts."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ArtifactMetadata:
    """Metadata describing an enriched bar artifact without returning bars."""

    artifact_id: str
    """Stable artifact identifier."""

    symbol: str = ""
    """Symbol represented by the artifact."""

    source: str = ""
    """Data source, such as yfinance or hyperliquid."""

    interval: str = ""
    """Bar interval represented by the artifact."""

    mode: str = ""
    """Computation mode used to create the artifact."""

    timeframe_alias: str = "primary"
    """Strategy timeframe alias represented by the artifact."""

    status: str = ""
    """Artifact job status."""

    bar_count: int = 0
    """Number of bars stored in the artifact."""

    start_date: str = ""
    """First bar timestamp, if known."""

    end_date: str = ""
    """Last bar timestamp, if known."""

    columns: list[str] = field(default_factory=list)
    """Columns available in the artifact bars."""

    indicators_applied: list[str] = field(default_factory=list)
    """Indicators applied before persisting the artifact."""

    features_applied: list[str] = field(default_factory=list)
    """Features applied before persisting the artifact."""

    null_counts: dict[str, int] = field(default_factory=dict)
    """Count of null values by column."""

    created_at: str = ""
    """Artifact creation timestamp."""

    expires_at: str | None = None
    """Expiration timestamp, or None for durable artifacts."""

    retention_policy: str = "durable_until_deleted"
    """Retention policy for the persisted artifact."""
