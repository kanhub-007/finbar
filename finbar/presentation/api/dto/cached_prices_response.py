"""Response for cached price queries."""

from pydantic import BaseModel

from finbar.presentation.api.dto.price_bar_response import PriceBarResponse


class CachedPricesResponse(BaseModel):
    symbol: str
    source: str
    interval: str
    bar_count: int
    bars: list[PriceBarResponse]
