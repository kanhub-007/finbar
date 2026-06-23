"""UnknownMetricError — moved to ``domain.entities``.

This module re-exports the error for backward compatibility with code that
still imports ``from finbar_strategy_runtime.domain.services.unknown_metric_error
import UnknownMetricError``. New code should import from
``finbar_strategy_runtime.domain.entities.unknown_metric_error``.
"""

from finbar_strategy_runtime.domain.entities.unknown_metric_error import (
    UnknownMetricError,
)

__all__ = ["UnknownMetricError"]
