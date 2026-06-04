"""Data source enum for OHLCV price data.

Copied from h_stocks/core/domain/models.py:DataSource enum.
YFINANCE is v1, HYPERLIQUID is v2.
"""

from enum import StrEnum


class DataSource(StrEnum):
    """Data source for price data."""

    YFINANCE = "yfinance"
    HYPERLIQUID = "hyperliquid"
