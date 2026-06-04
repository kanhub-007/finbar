"""Application-layer DTOs — data crossing layer boundaries.

Pure dataclasses, no behavior, no ORM, no domain logic.
"""

from finbar.core.application.dto.apply_indicators_request import (
    ApplyIndicatorsRequest,
)
from finbar.core.application.dto.apply_indicators_result import (
    ApplyIndicatorsResult,
)
from finbar.core.application.dto.backtest_request import BacktestRequest
from finbar.core.application.dto.backtest_result import BacktestResultDTO

__all__ = [
    "ApplyIndicatorsRequest",
    "ApplyIndicatorsResult",
    "BacktestRequest",
    "BacktestResultDTO",
]
