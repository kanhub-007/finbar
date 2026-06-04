"""Pydantic request models for the Finbar REST API.

Separate from domain DTOs — these handle HTTP serialization/validation.
"""

from pydantic import BaseModel, Field


class FetchPricesRequest(BaseModel):
    """Request body for starting a background price fetch."""

    symbol: str = Field(..., description="Ticker symbol (e.g., AAPL)")
    source: str = Field(default="yfinance", description="Data source")
    interval: str = Field(default="1d", description="Time interval")
    start_date: str | None = Field(None, description="Start date (ISO format)")
    end_date: str | None = Field(None, description="End date (ISO format)")


class CachedPricesQuery(BaseModel):
    """Query params for cached price retrieval."""

    symbol: str = Field(..., description="Ticker symbol")
    source: str = Field(default="yfinance", description="Data source")
    interval: str = Field(default="1d", description="Time interval")
    start_date: str | None = Field(None, description="Start date (ISO format)")
    end_date: str | None = Field(None, description="End date (ISO format)")
