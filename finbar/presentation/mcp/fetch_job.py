"""FetchJob domain entity — background fetch job state.

Dataclass shape adapted from kapsula/presentation/mcp/search_job.py:SearchJob.
"""

from dataclasses import dataclass


@dataclass
class FetchJob:
    """Background fetch job state.

    Created when a client requests fresh data from yfinance or another
    rate-limited source. The job runs in a background task; the client
    polls for progress and retrieves results when complete.
    """

    job_id: str
    status: str = "queued"
    symbol: str = ""
    source: str = ""
    interval: str = ""
    start_date: str | None = None
    end_date: str | None = None
    progress_pct: int = 0
    result: str | None = None
    error: str | None = None
