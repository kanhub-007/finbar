"""Symbol metadata in API responses."""

from pydantic import BaseModel


class SymbolInfoResponse(BaseModel):
    symbol: str
    company_name: str = ""
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    market_cap: float | None = None
