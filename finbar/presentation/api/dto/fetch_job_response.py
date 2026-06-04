"""Response when a background fetch job is created."""

from pydantic import BaseModel


class FetchJobResponse(BaseModel):
    job_id: str
    symbol: str
    source: str
    interval: str
    status: str
