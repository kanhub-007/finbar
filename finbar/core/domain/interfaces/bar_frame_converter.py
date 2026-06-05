"""BarFrameConverter interface — converts bar DTOs to tabular frames."""

from abc import ABC, abstractmethod
from typing import Any


class BarFrameConverter(ABC):
    """Converts JSON-safe OHLCV bar dictionaries to and from frame objects."""

    @abstractmethod
    def bars_to_frame(self, bars: list[dict]) -> Any:
        """Convert bar dictionaries to an implementation-specific frame."""
        ...

    @abstractmethod
    def frame_to_bars(self, frame: Any) -> list[dict]:
        """Convert an implementation-specific frame back to bar dictionaries."""
        ...
