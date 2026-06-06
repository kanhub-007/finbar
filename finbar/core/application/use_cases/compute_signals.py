"""ComputeSignalsUseCase — apply signal interpretation to enriched bars."""

import logging
from typing import Any

from finbar.core.application.dto.compute_signals_request import ComputeSignalsRequest
from finbar.core.domain.interfaces.bar_frame_converter import BarFrameConverter
from finbar.core.domain.interfaces.signal_calculator import SignalCalculator

logger = logging.getLogger(__name__)


class ComputeSignalsUseCase:
    """Compute signal interpretation columns from enriched bar data.

    Reads enriched bars, converts to DataFrame, applies the signal
    calculator, and returns enriched bars with signal columns added.
    Synchronous — no background job needed for pure pandas computation.
    """

    def __init__(
        self,
        calculator: SignalCalculator,
        converter: BarFrameConverter,
    ):
        """Create the use case with injected calculator and converter."""
        self._calculator = calculator
        self._converter = converter

    def execute(self, request: ComputeSignalsRequest) -> dict[str, Any]:
        """Apply signal interpretation and return enriched bar dicts.

        Args:
            request: Contains the enriched bars to process.

        Returns:
            Dict with enriched bars, bar_count, and signal columns applied.
        """
        frame = self._converter.bars_to_frame(request.bars)
        enriched = self._calculator.calculate(frame)
        bars = self._converter.frame_to_bars(enriched)

        signal_columns = [
            "rsi_zone",
            "adx_conviction",
            "is_squeeze",
            "is_overextended",
            "is_weak_trend",
            "is_low_volume",
            "near_resistance",
            "near_support",
            "confidence_score",
        ]

        return {
            "symbol": request.symbol,
            "interval": request.interval,
            "bar_count": len(bars),
            "signal_columns": signal_columns,
            "bars": bars,
        }
