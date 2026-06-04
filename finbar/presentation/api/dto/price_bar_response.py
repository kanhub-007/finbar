"""A single OHLCV price bar in API responses."""

from pydantic import BaseModel


class PriceBarResponse(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None
