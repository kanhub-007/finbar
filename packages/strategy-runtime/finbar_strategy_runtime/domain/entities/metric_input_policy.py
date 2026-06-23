"""MetricInputPolicy — how missing required metric inputs are handled.

Strictness contract (spec 2026-06-23):

- ``STRICT``: raise :class:`MetricDependencyError` on any missing required
  dependency. This is the live-parity default.
- ``WARN_AND_NAN``: explicitly requested research/reporting path. Missing
  required deps emit NaN/UNKNOWN plus a recorded warning rather than raising.
- ``RESEARCH_COMPAT``: preserves legacy silent-default behaviour only when
  a caller explicitly opts into it.
"""

from __future__ import annotations

from enum import Enum


class MetricInputPolicy(Enum):
    """Policy for handling missing required metric dependencies."""

    STRICT = "strict"
    WARN_AND_NAN = "warn_and_nan"
    RESEARCH_COMPAT = "research_compat"


#: The default policy. Live-parity workflows must use STRICT.
DEFAULT_METRIC_INPUT_POLICY = MetricInputPolicy.STRICT


__all__ = ["MetricInputPolicy", "DEFAULT_METRIC_INPUT_POLICY"]
