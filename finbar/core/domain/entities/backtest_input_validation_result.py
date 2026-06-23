"""BacktestInputValidationResult — DTO for backtest bar input validation.

Returned by :class:`BacktestInputValidator` implementations. Typed
dataclass so callers use attribute access and so adding a field is a
one-line change rather than a dict-literal edit across call sites.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BacktestInputValidationResult:
    """Result of validating raw backtest bar dicts before execution."""

    valid: bool
    """True when the bars pass every input check."""

    errors: list[str] = field(default_factory=list)
    """Human-readable validation errors (empty when ``valid``)."""

    bar_count: int = 0
    """Number of bars inspected."""

    has_timestamp: bool = False
    """True when every bar carries a parseable ``timestamp``."""

    interval_known: bool = False
    """True when the supplied interval resolves to a known annualization."""

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict."""
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "bar_count": self.bar_count,
            "has_timestamp": self.has_timestamp,
            "interval_known": self.interval_known,
        }


__all__ = ["BacktestInputValidationResult"]
