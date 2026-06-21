"""UnknownMetricError — raised for metrics outside the unified catalog."""


class UnknownMetricError(ValueError):
    """Raised when a metric name is not present in the streaming matrix."""
