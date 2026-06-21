"""FrameDependencyReport — whether a strategy uses frame-dependent indicators.

A pure value object describing whether the indicators a strategy requires
are frame-dependent (their row values change when more future rows are
supplied to the batch frame). Frame-dependent indicators make the legacy
``batch_full_frame`` enrichment unsafe as a live-parity oracle.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FrameDependencyReport:
    """Report on a strategy's use of frame-dependent indicators."""

    indicators: list[str] = field(default_factory=list)
    """Frame-dependent indicator names the strategy requires (e.g. vp_poc)."""

    live_parity_safe: bool = True
    """True if the enrichment is safe for live parity given the mode.

    Computed by the classifier from the mode + whether frame-dependent
    indicators are present.
    """

    reason: str = ""
    """Human-readable explanation of the live-parity-safety verdict."""
