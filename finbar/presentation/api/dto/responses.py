"""Pydantic response models for the Finbar REST API."""

from pydantic import BaseModel


class PriceBarResponse(BaseModel):
    """A single OHLCV price bar in API responses."""

    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None


class SymbolInfoResponse(BaseModel):
    """Symbol metadata in API responses."""

    symbol: str
    company_name: str = ""
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    market_cap: float | None = None


class CachedPricesResponse(BaseModel):
    """Response for cached price queries."""

    symbol: str
    source: str
    interval: str
    bar_count: int
    bars: list[PriceBarResponse]


class FetchJobResponse(BaseModel):
    """Response when a background fetch job is created."""

    job_id: str
    symbol: str
    source: str
    interval: str
    status: str


class JobStatusResponse(BaseModel):
    """Response for job status queries."""

    job_id: str
    symbol: str
    source: str
    interval: str
    status: str
    progress_pct: int = 0
    bar_count: int = 0
    error: str | None = None


class DeleteResponse(BaseModel):
    """Response for delete operations."""

    symbol: str
    deleted_count: int


class SourcesResponse(BaseModel):
    """List of available data sources."""

    sources: list[str]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
