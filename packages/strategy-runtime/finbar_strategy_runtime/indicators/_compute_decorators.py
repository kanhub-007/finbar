"""Metric compute decorators — cross-cutting concerns for indicator compute.

The indicator compute path (windowed state, batch calculator) repeatedly
needs the same cross-cutting behaviour around the actual compute call:

- Catch any exception from a pandas_ta / handler function and return NaN
  (with a logged warning) instead of silently propagating or silently
  swallowing.

These concerns are expressed as decorators that wrap a
``ComputeCallable`` so the compute logic stays clean and the policy lives
in exactly one place.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pandas as pd

from finbar_strategy_runtime.indicators._handler_registry import HandlerRegistry

logger = logging.getLogger(__name__)

#: A function that computes one metric on a frame and returns a mapping
#: ``{name: column_or_scalar}``.
ComputeCallable = Callable[..., dict]
MetricResult = "float | dict[str, float]"


def _last_value(value: object) -> float:
    """Return the scalar value at the end of *value*.

    Accepts a pandas Series (``.iloc[-1]``) or any scalar coercible to
    float. Returns NaN for None.
    """
    if value is None:
        return float("nan")
    if hasattr(value, "iloc"):
        return float(value.iloc[-1])
    return float(value)


def log_failures_as_nan(name: str, compute: ComputeCallable) -> ComputeCallable:
    """Wrap *compute* so failures log a warning and return NaN.

    Args:
        name: Metric name (for the log message).
        compute: The compute callable to wrap.

    Returns:
        A callable with the same signature that never raises — on any
        exception it logs at WARNING with ``exc_info=True`` and returns
        ``float("nan")``.
    """

    def wrapper(*args, **kwargs):
        try:
            return compute(*args, **kwargs)
        except Exception:
            logger.warning(
                "Failed to compute metric %r", name, exc_info=True
            )
            return float("nan")

    return wrapper


def last_value_or_nan(compute: ComputeCallable, name: str) -> ComputeCallable:
    """Wrap *compute* (returns a column dict) so it yields the last scalar.

    The wrapped callable computes the metric, extracts
    ``result[name]``, and returns its last value. Any failure is delegated
    to :func:`log_failures_as_nan` (compose the two for full safety).
    """

    def wrapper(*args, **kwargs) -> float:
        result = compute(*args, **kwargs)
        col = result[name] if isinstance(result, dict) else result
        return _last_value(col)

    return wrapper


def resolve_last_value_compute(
    name: str,
    handlers: HandlerRegistry,
) -> Callable[[pd.DataFrame], float] | None:
    """Resolve *name* to a callable returning the last-bar scalar, or None.

    Selects exactly one compute strategy by predicate (mutually exclusive):

    1. registered handler  → ``handler(df, name, cache)``
    2. dynamic indicator   → ``_compute_dynamic(df, name)``
    3. rolling VP indicator → ``_compute_rolling_vp_dynamic(df, name, {})``

    The returned callable already:
    - extracts ``result[name]`` and returns its last value, and
    - logs any failure at WARNING and returns NaN (never raises).

    Returns None when no strategy matches (caller decides the fallback).
    """
    from finbar_strategy_runtime.indicators._dynamic_dispatch import (
        _compute_dynamic,
        _compute_rolling_vp_dynamic,
        _is_dynamic,
        _is_rolling_vp,
    )

    if name in handlers:
        handler, _requires = handlers[name]

        def _via_handler(df: pd.DataFrame) -> float:
            result = handler(df, name, {})
            return _last_value(result[name])

        return log_failures_as_nan(name, _via_handler)

    if _is_dynamic(name):

        def _via_dynamic(df: pd.DataFrame) -> float:
            result = _compute_dynamic(df.copy(), name)
            return _last_value(result[name])

        return log_failures_as_nan(name, _via_dynamic)

    if _is_rolling_vp(name):

        def _via_rvp(df: pd.DataFrame) -> float:
            result = _compute_rolling_vp_dynamic(df.copy(), name, {})
            return _last_value(result[name])

        return log_failures_as_nan(name, _via_rvp)

    return None


__all__ = [
    "ComputeCallable",
    "log_failures_as_nan",
    "resolve_last_value_compute",
    "_last_value",
]
