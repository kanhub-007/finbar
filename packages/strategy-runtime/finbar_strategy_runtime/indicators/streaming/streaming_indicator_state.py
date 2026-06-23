"""StreamingIndicatorState — ABC for incremental per-indicator state objects.

Every streaming state class (SmaState, EmaState, …, WindowedIndicatorState,
BatchedWindowedState, PrefixRecomputeIndicatorState, …) implements this
interface so the engine can treat them uniformly via the type system rather
than duck typing.

Two read shapes exist in practice:

- Single-output states expose ``value`` (e.g. ``SmaState``).
- Multi-output states expose named properties (e.g. ``MacdState.macd`` /
  ``.signal`` / ``.hist``, ``BbState.upper`` / ``.middle`` / ``.lower``,
  ``IncrementalSessionVpState.poc`` / ``.vah`` / ``.val``).
- Batched/windowed states expose ``values`` (a dict).

The engine's ``_read_output`` reads the right attribute per family, so this
ABC only mandates the write/lifecycle methods (``update``, ``reset``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StreamingIndicatorState(ABC):
    """Lifecycle interface for incremental indicator state objects."""

    @abstractmethod
    def update(self, bar: dict[str, Any]) -> Any:
        """Ingest one closed OHLCV bar; return the latest value(s)."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Clear accumulated state so the instance can be reused."""
        ...


__all__ = ["StreamingIndicatorState"]
