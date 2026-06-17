"""StreamingIndicatorCalculator — compute indicators one bar at a time.

Pure computation contract. Implementations maintain bounded per-indicator
state and expose the latest-row scalar values. Used by live / intrabar
runtimes instead of the batch ``IndicatorCalculator.calculate()``.
"""

from abc import ABC, abstractmethod

from finbar_strategy_runtime.domain.entities.latest_bar import LatestBar


class StreamingIndicatorCalculator(ABC):
    """Compute indicators one bar at a time with bounded state.

    The contract is incremental: callers feed closed bars in order and
    read the latest-row scalar values. Per-bar cost for a streaming
    indicator is O(indicator-cost); for a windowed indicator it is
    O(window). Neither depends on the total number of bars seen.
    """

    @abstractmethod
    def update(self, bar: dict) -> LatestBar:
        """Ingest one OHLCV bar; return the latest-row snapshot.

        Args:
            bar: Dict with keys ``open, high, low, close, volume``
                and optionally ``timestamp``.

        Returns:
            LatestBar snapshot containing all computed indicator values.
        """

    @abstractmethod
    def latest(self) -> LatestBar:
        """Return the most recent snapshot without ingesting a bar.

        Returns:
            The LatestBar from the most recent ``update()`` call, or
            an empty LatestBar if no bars have been ingested.
        """

    @abstractmethod
    def is_ready(self) -> bool:
        """True once at least MIN_BARS bars have been ingested."""

    @abstractmethod
    def reset(self) -> None:
        """Clear all per-indicator state (parity with on_reset)."""
