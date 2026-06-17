"""Handler registry — shared dispatch table for indicator handlers.

This module is the single source of truth for the indicator dispatch table.
Every handler module imports ``_register`` and ``_safe_ta`` from here.
Importing any handler module triggers its ``@_register`` decorators,
populating ``_INDICATOR_HANDLERS`` at import time.
"""

import logging
from collections.abc import Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _safe_ta(func: Callable, *args, **kwargs) -> pd.Series | None:
    """Call a pandas_ta function and return None-safe result.

    pandas_ta returns None when there are fewer bars than the requested
    period length. This helper converts None to a NaN-filled Series.
    Also masks the first N bars to NaN (warmup) when ``length=`` is
    provided, guarding against functions like ``ta.rsi`` that return
    partial Series with misleading values (e.g. 0.0) instead of None.
    """
    try:
        result = func(*args, **kwargs)
    except Exception:
        result = None
    if result is None:
        series = args[0] if args else kwargs.get("close")
        if series is not None and isinstance(series, pd.Series):
            return pd.Series(float("nan"), index=series.index, dtype="float64")
        return None

    # Mask warmup bars: first N bars → NaN where N = lookback period.
    # Some pandas_ta functions (e.g. ta.rsi) return partial Series instead
    # of None when there are fewer than ``length`` bars.
    lookback = kwargs.get("length")
    if (
        lookback is not None
        and isinstance(result, pd.Series)
        and len(result) > lookback
    ):
        result = result.copy()
        result.iloc[:lookback] = np.nan

    return result


_INDICATOR_HANDLERS: dict[str, tuple[Callable, set[str]]] = {}


def _register(name: str, requires: set[str] | None = None):
    """Decorator to register an indicator handler.

    Populates ``_INDICATOR_HANDLERS`` which ``UnifiedMetricCatalog`` reads
    at construction time to determine which metrics are computable.
    """

    def decorator(func: Callable):
        _INDICATOR_HANDLERS[name] = (func, requires or set())
        return func

    return decorator
