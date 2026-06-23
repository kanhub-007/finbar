"""Execution-config enums — canonical allowed values for string config fields.

``ExecutionConfig`` keeps its fields as ``str`` (so YAML/JSON-driven
construction is unchanged), but these enums are the single source of the
allowed value sets. ``ExecutionConfig.__post_init__`` validates against
them so a typo (e.g. ``margin_mode="ful"``) raises immediately instead of
silently falling through to default behaviour.
"""

from __future__ import annotations

from enum import Enum


class RiskMode(str, Enum):
    """How the risk budget scales with leverage."""

    FIXED_EQUITY_RISK = "fixed_equity_risk"
    LEVERAGE_SCALED_RISK = "leverage_scaled_risk"


class MarginMode(str, Enum):
    """Margin accounting mode."""

    SIMPLIFIED = "simplified"
    FULL = "full"


class RiskPriceBasis(str, Enum):
    """Anchor for stop/target prices."""

    SIGNAL_CLOSE = "signal_close"
    ENTRY_FILL = "entry_fill"


class BorrowTimeBasis(str, Enum):
    """Borrow-cost holding-period granularity."""

    CALENDAR_DAY = "calendar_day"
    TIMESTAMP_DELTA = "timestamp_delta"


class MarketCalendar(str, Enum):
    """Calendar used for annualization and session logic."""

    EQUITY_REGULAR_HOURS = "equity_regular_hours"
    CRYPTO_24_7 = "crypto_24_7"


__all__ = [
    "RiskMode",
    "MarginMode",
    "RiskPriceBasis",
    "BorrowTimeBasis",
    "MarketCalendar",
]
