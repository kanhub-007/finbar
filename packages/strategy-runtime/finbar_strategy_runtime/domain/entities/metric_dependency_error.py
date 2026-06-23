"""MetricDependencyError — raised when a metric's required inputs are absent.

Distinct from a warmup condition (enough history) and from an optional
input default: a ``MetricDependencyError`` means a required dependency
column is genuinely missing and the metric refuses to substitute a
neutral/false/zero value for it.
"""

from __future__ import annotations


class MetricDependencyError(ValueError):
    """A required metric dependency column is missing from the frame.

    Attributes:
        metric_name: The metric whose requirement was violated.
        missing: The required column(s) that were absent.
        reason: Human-readable explanation.
    """

    def __init__(
        self,
        metric_name: str,
        missing: list[str],
        reason: str = "",
    ) -> None:
        """Create the error for *metric_name* missing *missing* columns.

        Args:
            metric_name: Metric that requires the missing columns.
            missing: Required column names absent from the frame.
            reason: Optional extra context.
        """
        self.metric_name = metric_name
        self.missing = list(missing)
        self.reason = reason
        cols = ", ".join(missing)
        msg = (
            f"Metric '{metric_name}' requires missing column(s): {cols}."
        )
        if reason:
            msg = f"{msg} {reason}"
        super().__init__(msg)


__all__ = ["MetricDependencyError"]
