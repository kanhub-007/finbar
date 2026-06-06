"""SignalCalculator — domain interface for signal interpretation.

Computes derived signal columns from already‑enriched OHLCV bars.
Separate from indicator calculation — signals interpret indicators,
they don't compute new ones from raw price data.
"""

from abc import ABC, abstractmethod
from typing import Any


class SignalCalculator(ABC):
    """Compute signal interpretation columns from enriched bar data.

    Takes a DataFrame with OHLCV + indicator columns and adds derived
    signal columns such as RSI zones, risk flags, and confidence scores.
    Implementations are pandas‑based but the interface is generic.
    """

    @abstractmethod
    def calculate(self, frame: Any) -> Any:
        """Add signal interpretation columns and return the enriched frame.

        Args:
            frame: DataFrame with columns [open, high, low, close, volume]
                plus any indicator columns needed for signal computation
                (rsi_14, adx, atr, rvol, swing_high_20, swing_low_20, etc.).

        Returns:
            DataFrame with additional signal columns appended.
        """
        ...
