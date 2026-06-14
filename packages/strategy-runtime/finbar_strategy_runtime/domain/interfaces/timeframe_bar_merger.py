"""TimeframeBarMerger interface — merges primary and informative frames."""

from abc import ABC, abstractmethod
from typing import Any


class TimeframeBarMerger(ABC):
    """Merge informative timeframe columns into a primary timeframe frame."""

    @abstractmethod
    def merge(
        self,
        primary: Any,
        informative: Any,
        informative_interval: str,
        columns: list[str] | None = None,
    ) -> Any:
        """Return primary frame enriched with informative timeframe columns."""
        ...
