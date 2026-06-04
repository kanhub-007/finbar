"""Pydantic request models for the Finbar REST API.

One class per file — re-exported here for convenient importing.
Separate from domain DTOs — these handle HTTP serialization/validation.
"""

from finbar.presentation.api.dto.apply_indicators_request import (
    ApplyIndicatorsRequest,
)
from finbar.presentation.api.dto.backtest_request import BacktestRequest
from finbar.presentation.api.dto.cached_prices_query import CachedPricesQuery
from finbar.presentation.api.dto.fetch_prices_request import FetchPricesRequest

__all__ = [
    "ApplyIndicatorsRequest",
    "BacktestRequest",
    "CachedPricesQuery",
    "FetchPricesRequest",
]
