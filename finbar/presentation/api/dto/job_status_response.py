"""Response for job status queries."""

from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    job_id: str
    symbol: str
    source: str
    interval: str
    status: str
    progress_pct: int = 0
    bar_count: int = 0
    error: str | None = None
