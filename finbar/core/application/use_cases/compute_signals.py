"""ComputeSignalsUseCase — apply signal interpretation to enriched bars."""

import logging

from finbar.core.application.dto.compute_signals_request import ComputeSignalsRequest
from finbar.core.application.dto.compute_signals_result import ComputeSignalsResult
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

    def execute(self, request: ComputeSignalsRequest) -> ComputeSignalsResult:
        """Apply signal interpretation and return enriched bar dicts."""
        frame = self._converter.bars_to_frame(request.bars)
        enriched = self._calculator.calculate(frame)
        bars = self._converter.frame_to_bars(enriched)

        return ComputeSignalsResult(
            bars=bars,
            symbol=request.symbol,
            interval=request.interval,
            bar_count=len(bars),
        )
