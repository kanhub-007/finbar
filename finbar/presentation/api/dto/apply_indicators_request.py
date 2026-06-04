"""Request body for applying technical indicators."""

from pydantic import BaseModel, Field


class ApplyIndicatorsRequest(BaseModel):
    bars: list[dict] = Field(..., description="List of OHLCV bar dicts")
    indicators: list[str] = Field(..., description="Indicator names to compute")
