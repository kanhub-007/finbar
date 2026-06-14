"""Result of a Market Profile (TPO) computation for one trading session.

A pure dataclass — no behavior, no ORM, no domain logic beyond data
holding. Used as a return value from market profile computation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MarketProfileResult:
    """Result of a Market Profile computation for one session."""

    poc: float
    """Point of Control — price level with the most TPOs (most time spent)."""

    vah: float
    """Value Area High — upper bound of 68% TPO zone."""

    val: float
    """Value Area Low — lower bound of 68% TPO zone."""

    total_tpos: int
    """Total number of TPO periods in the session."""

    value_area_tpos: int
    """TPO count within the Value Area."""

    bucket_size: float
    """Price increment per bucket."""

    num_buckets: int
    """Number of price buckets in the profile."""

    profile: dict[float, int] = field(default_factory=dict)
    """Price → TPO count mapping for the full profile."""
