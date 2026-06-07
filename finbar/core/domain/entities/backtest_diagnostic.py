"""BacktestDiagnostic — structured diagnostics for execution issues."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BacktestDiagnostic:
    """Structured diagnostic emitted during backtest execution."""

    severity: str
    """Diagnostic severity such as info, warning, or order_rejected."""

    code: str
    """Stable machine-readable diagnostic code."""

    message: str
    """Human-readable explanation."""

    date: str = ""
    """Timestamp associated with the diagnostic, if available."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional structured context."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable diagnostic dict."""
        payload: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "date": self.date,
            "message": self.message,
        }
        payload.update(self.metadata)
        return payload
