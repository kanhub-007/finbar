"""ApplyIndicatorsUseCase — apply technical indicators to raw OHLCV bars.

Depends on IndicatorCalculator (Strategy pattern — domain interface).
Converts bars (list of dicts) ↔ DataFrame for the calculator, then
returns enriched bars as JSON-serializable dicts.
"""

import logging

from finbar.core.application.bar_utils import bars_to_dataframe, dataframe_to_bars
from finbar.core.application.dto.apply_indicators_request import (
    ApplyIndicatorsRequest,
)
from finbar.core.application.dto.apply_indicators_result import (
    ApplyIndicatorsResult,
)
from finbar.core.domain.interfaces.indicator_calculator import (
    IndicatorCalculator,
)

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}


class ApplyIndicatorsUseCase:
    """Apply requested technical indicators to a set of OHLCV bars.

    Pure computation — no I/O, no caching. Receives bars as input,
    returns enriched bars. The AI client composes this with
    get_cached_prices and run_backtest.
    """

    def __init__(self, calculator: IndicatorCalculator):
        """Constructor injection — receives indicator calculator.

        Args:
            calculator: IndicatorCalculator implementation (e.g. pandas_ta).
        """
        self._calculator = calculator

    def execute(self, request: ApplyIndicatorsRequest) -> ApplyIndicatorsResult:
        """Apply indicators to bars and return enriched result.

        Args:
            request: ApplyIndicatorsRequest with bars and indicator names.

        Returns:
            ApplyIndicatorsResult with enriched bars.
        """
        # 1. Validate input
        if not request.bars:
            return ApplyIndicatorsResult(
                error="No bars provided",
            )

        if not request.indicators:
            return ApplyIndicatorsResult(
                bars=list(request.bars),
                bar_count=len(request.bars),
            )

        # 2. Convert bars to DataFrame
        try:
            df = bars_to_dataframe(request.bars)
        except Exception as e:
            logger.warning("Failed to convert bars to DataFrame: %s", e)
            return ApplyIndicatorsResult(error=f"Invalid bar data: {e}")

        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            return ApplyIndicatorsResult(
                error=f"Missing required columns: {', '.join(sorted(missing))}",
            )

        # 3. Compute indicators
        try:
            enriched_df = self._calculator.calculate(df, request.indicators)
        except Exception as e:
            logger.exception("Indicator calculation failed")
            return ApplyIndicatorsResult(
                error=f"Calculation error: {e}",
            )

        # 4. Convert back to list of dicts
        enriched_bars = dataframe_to_bars(enriched_df)

        return ApplyIndicatorsResult(
            bars=enriched_bars,
            indicators_applied=list(request.indicators),
            bar_count=len(enriched_bars),
        )
