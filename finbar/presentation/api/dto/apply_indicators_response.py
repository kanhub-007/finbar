"""Response from apply_indicators."""

from pydantic import BaseModel


class ApplyIndicatorsResponse(BaseModel):
    bar_count: int
    indicators_applied: list[str]
    bars: list[dict]
