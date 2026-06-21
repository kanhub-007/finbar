"""Frame-dependency classification for strategy indicator sets.

A frame-dependent indicator's row value changes when the caller supplies
more future rows to the batch frame. Session Volume Profile
(``vp_poc``/``vp_vah``/``vp_val``), Market Profile (``mp_*``), Composite VP
(``cvp_*``), and the AMT auction-state/signals derived from them fall in
this category because they broadcast a completed-session profile to every
row in the session.

Rolling bar-window indicators (``rvp_*``) are NOT frame-dependent — they
use a fixed trailing window.

This classifier is owned by the package (ADR-3) so Finbar and Finbot
agree on what "live-parity safe" means.
"""

from __future__ import annotations

from finbar_strategy_runtime.domain.entities.frame_dependency_report import (
    FrameDependencyReport,
)

# Roots of frame-dependence: session-grouped VP/MP/CVP families and the
# AMT auction-state/signals derived from them. Rolling bar-window
# indicators (rvp_*) are intentionally excluded.
_FRAME_DEPENDENT_PREFIXES = ("vp_", "mp_", "cvp_")
_FRAME_DEPENDENT_DERIVED = frozenset(
    {
        "inside_value",
        "above_value",
        "below_value",
        "at_poc",
        "near_vah",
        "near_val",
        "distance_to_vah_pct",
        "distance_to_val_pct",
        "value_area_width_pct",
        "balance_status",
        "acceptance_into_value",
        "rejection_from_edge",
        "acceptance_outside_value",
        "poc_rejection",
        "edge_volume_building",
        "value_area_migration",
        "wyckoff_phase",
        "profile_shape",
    }
)
# Dynamic session-count slopes (poc_slope_N) are also frame-dependent.
_FRAME_DEPENDENT_DYNAMIC_PREFIXES = ("poc_slope_",)


def is_frame_dependent_indicator(name: str) -> bool:
    """Return True if *name* is a frame-dependent indicator."""
    if name in _FRAME_DEPENDENT_DERIVED:
        return True
    if any(name.startswith(p) for p in _FRAME_DEPENDENT_PREFIXES):
        return True
    return any(name.startswith(p) for p in _FRAME_DEPENDENT_DYNAMIC_PREFIXES)


def classify_frame_dependency(
    indicator_names: list[str], enrichment_mode: str
) -> FrameDependencyReport:
    """Classify a strategy's live-parity safety for the given enrichment mode.

    Args:
        indicator_names: All indicators the strategy requires (primary +
            informative, concrete names).
        enrichment_mode: ``"batch_full_frame"`` or
            ``"live_parity_streaming"``.

    Returns:
        A FrameDependencyReport naming the frame-dependent indicators
        present and stating whether the mode is live-parity safe.
    """
    present = [n for n in indicator_names if is_frame_dependent_indicator(n)]
    if enrichment_mode == "live_parity_streaming":
        return FrameDependencyReport(
            indicators=present,
            live_parity_safe=True,
            reason="live_parity_streaming mode uses a causal enricher; no"
            " future bars influence any row.",
        )
    if not present:
        return FrameDependencyReport(
            indicators=[],
            live_parity_safe=True,
            reason="batch_full_frame mode with no frame-dependent indicators.",
        )
    return FrameDependencyReport(
        indicators=present,
        live_parity_safe=False,
        reason="batch_full_frame mode computes session VP/AMT over the full"
        " frame, broadcasting completed-session values to earlier rows"
        " (future leakage).",
    )
