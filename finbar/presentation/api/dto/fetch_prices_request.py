"""Request body for starting a background price fetch."""

from pydantic import BaseModel, Field


class FetchPricesRequest(BaseModel):
    symbol: str = Field(..., description="Ticker symbol (e.g., AAPL)")
    source: str = Field(default="yfinance", description="Data source")
    interval: str = Field(default="1d", description="Time interval")
    start_date: str | None = Field(None, description="Start date (ISO format)")
    end_date: str | None = Field(None, description="End date (ISO format)")
