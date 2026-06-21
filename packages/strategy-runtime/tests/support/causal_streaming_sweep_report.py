"""CausalStreamingSweepReport — result of coverage-matrix sweep tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CausalStreamingSweepReport:
    """Summarises unsupported causal streaming metric classifications."""

    unsupported: list[str] = field(default_factory=list)
    silent_wrong: list[str] = field(default_factory=list)
    loud_nan_mismatch: list[str] = field(default_factory=list)
