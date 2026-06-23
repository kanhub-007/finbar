"""Handler registry — shared dispatch table for indicator handlers.

This module is the single source of truth for the indicator dispatch table.
Every handler module imports ``_register`` and ``_safe_ta`` from here.
Importing any handler module triggers its ``@_register`` decorators,
populating the module-level ``_INDICATOR_HANDLERS`` registry at import time.

Consumers (``UnifiedMetricCatalog``, ``StreamingIndicatorEngine``,
``PandasTaIndicatorCalculator``) receive a ``HandlerRegistry`` via
Constructor Injection — typically the result of
``default_handler_registry()``. Tests may construct a ``HandlerRegistry``
and register stub handlers to exercise consumers without importing the
full handler set.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

HandlerEntry = tuple[Callable, set[str]]


class HandlerRegistry:
    """Typed, injectable registry of indicator handlers.

    Behaves as a read-only mapping ``name -> (handler, requires)`` so
    existing ``name in registry`` / ``registry[name]`` call sites work
    unchanged. Population happens via :meth:`register` (used by the
    ``_register`` decorator) before first use.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, HandlerEntry] = {}

    def register(
        self,
        name: str,
        handler: Callable,
        requires: set[str] | None = None,
    ) -> None:
        """Register (or replace) the handler for *name*."""
        self._handlers[name] = (handler, requires or set())

    def pop(self, name: str, default: object = None) -> HandlerEntry | None:
        """Remove and return the entry for *name*, or *default*."""
        return self._handlers.pop(name, default)

    def get(self, name: str) -> HandlerEntry | None:
        """Return the entry for *name*, or None."""
        return self._handlers.get(name)

    def names(self) -> set[str]:
        """Return a copy of all registered handler names."""
        return set(self._handlers)

    # ── mapping protocol (read-only) ───────────────────────────────────

    def __contains__(self, name: object) -> bool:
        return name in self._handlers

    def __getitem__(self, name: str) -> HandlerEntry:
        return self._handlers[name]

    def __setitem__(self, name: str, entry: HandlerEntry) -> None:
        """Register via ``registry[name] = (handler, requires)``.

        Provided so existing decorator/test call sites that assign a
        ``(handler, requires)`` tuple keep working.
        """
        handler, requires = entry
        self._handlers[name] = (handler, set(requires))

    def keys(self):
        return self._handlers.keys()

    def items(self):
        return self._handlers.items()

    def __iter__(self) -> Iterator[str]:
        return iter(self._handlers)

    def __len__(self) -> int:
        return len(self._handlers)


# Module-level registration sink. Decorators write here at import time.
# Consumers access it indirectly via :func:`default_handler_registry`.
_INDICATOR_HANDLERS: HandlerRegistry = HandlerRegistry()


def _register(name: str, requires: set[str] | None = None):
    """Decorator to register an indicator handler.

    Populates the module-level registry which ``UnifiedMetricCatalog`` reads
    at construction time to determine which metrics are computable.
    """

    def decorator(func: Callable):
        _INDICATOR_HANDLERS.register(name, func, requires)
        return func

    return decorator


def default_handler_registry() -> HandlerRegistry:
    """Return the default, fully-populated handler registry.

    Importing the handlers package triggers every ``@_register`` decorator,
    populating the module-level registry. Subsequent calls return the same
    cached registry instance (handlers register exactly once).
    """
    # Importing for its side effect: decorators populate _INDICATOR_HANDLERS.
    from finbar_strategy_runtime.indicators import handlers  # noqa: F401

    return _INDICATOR_HANDLERS


def _call_ta(func: Callable, *args, **kwargs):
    """Invoke *func*; return None on any exception (pandas_ta returns None
    when there are fewer bars than the requested period)."""
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


def _normalise_none(result, *args, **kwargs):
    """Convert a None result to a NaN-filled Series matching the input.

    Returns *result* unchanged when it is not None. When the input series
    cannot be located, returns None (caller must handle).
    """
    if result is not None:
        return result
    series = args[0] if args else kwargs.get("close")
    if series is not None and isinstance(series, pd.Series):
        return pd.Series(float("nan"), index=series.index, dtype="float64")
    return None


def _mask_warmup(result, *args, **kwargs):
    """Mask the first ``length`` bars to NaN.

    Guards against pandas_ta functions (e.g. ``ta.rsi``) that return a
    partial Series with misleading values instead of None when there are
    fewer than ``length`` bars.
    """
    lookback = kwargs.get("length")
    if (
        lookback is not None
        and isinstance(result, pd.Series)
        and len(result) > lookback
    ):
        result = result.copy()
        result.iloc[:lookback] = np.nan
    return result


def _safe_ta(func: Callable, *args, **kwargs) -> pd.Series | None:
    """Call a pandas_ta function with None-normalisation + warmup masking.

    Composed from three single-purpose steps (Decorator stack):

    1. :func:`_call_ta`        — invoke, return None on exception
    2. :func:`_normalise_none` — None → NaN-filled Series matching input
    3. :func:`_mask_warmup`    — mask first ``length`` bars to NaN

    Returns None only when the input series cannot be located.
    """
    result = _call_ta(func, *args, **kwargs)
    result = _normalise_none(result, *args, **kwargs)
    if result is None:
        return None
    return _mask_warmup(result, *args, **kwargs)


__all__ = [
    "HandlerRegistry",
    "HandlerEntry",
    "default_handler_registry",
]
