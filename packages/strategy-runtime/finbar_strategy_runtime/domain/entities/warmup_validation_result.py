"""WarmupValidationResult — DTO for required-data validation output.

Replaces the previously-untyped dict returned by
``RequiredDataValidator.validate``. Returning a typed dataclass means
callers use attribute access instead of string keys, and adding a field
is a one-line change rather than a three-way dict-literal edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WarmupValidationResult:
    """Result of checking strategy-required columns against an enriched frame."""

    warmup_bars: int
    """Index of the first tradable row (all required columns non-NaN)."""

    first_tradable: str
    """Timestamp of the first tradable row (ISO string, or empty)."""

    skipped_bars_due_to_warmup: int
    """Same value as ``warmup_bars``; kept for backward-compat naming."""

    skipped_bars_due_to_missing: int
    """Bars skipped *after* warmup due to missing values."""

    missing_after_warmup: list[str] = field(default_factory=list)
    """Columns still missing values after the warmup row."""

    no_tradable_bars: bool = False
    """True when no row is fully valid (entire frame is non-tradable)."""

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict (legacy dict-shape contract)."""
        return {
            "warmup_bars": self.warmup_bars,
            "first_tradable": self.first_tradable,
            "skipped_bars_due_to_warmup": self.skipped_bars_due_to_warmup,
            "skipped_bars_due_to_missing": self.skipped_bars_due_to_missing,
            "missing_after_warmup": list(self.missing_after_warmup),
            "no_tradable_bars": self.no_tradable_bars,
        }


__all__ = ["WarmupValidationResult"]
