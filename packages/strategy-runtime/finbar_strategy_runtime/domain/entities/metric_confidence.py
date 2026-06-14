"""MetricConfidence — classification of how reliable a metric computation is."""

from enum import Enum


class MetricConfidence(str, Enum):
    """Confidence level for a metric given the available data."""

    ACTUAL = "actual"
    PROXY = "proxy"
    APPROXIMATION = "approximation"
    UNAVAILABLE = "unavailable"
