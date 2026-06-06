"""ComputeSignalsResult — output DTO for signal interpretation."""

from dataclasses import dataclass, field

SIGNAL_COLUMNS: list[str] = [
    "rsi_zone",
    "adx_conviction",
    "is_squeeze",
    "is_overextended",
    "is_weak_trend",
    "is_low_volume",
    "near_resistance",
    "near_support",
    "confidence_score",
]
"""Canonical list of signal columns produced by the calculator."""


@dataclass(frozen=True)
class ComputeSignalsResult:
    """Output from signal interpretation — enriched bars with signal columns."""

    bars: list[dict] = field(default_factory=list)
    """Enriched bars with signal columns appended."""

    symbol: str = ""
    """Ticker symbol for metadata."""

    interval: str = ""
    """Bar interval for metadata."""

    bar_count: int = 0
    """Number of bars processed."""

    signal_columns: list[str] = field(default_factory=lambda: list(SIGNAL_COLUMNS))
    """Signal columns that were computed."""
