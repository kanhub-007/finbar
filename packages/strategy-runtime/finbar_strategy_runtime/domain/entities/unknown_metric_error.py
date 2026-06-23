"""UnknownMetricError — raised for metrics outside the unified catalog.

A domain error type. Lives in ``domain/entities`` (the innermost layer) so
that entities, services, and the parser can all raise/catch it without
inverting the dependency direction.
"""


class UnknownMetricError(ValueError):
    """Raised when a metric name is not present in the streaming matrix."""
