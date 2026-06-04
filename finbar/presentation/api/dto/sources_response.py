"""List of available data sources."""

from pydantic import BaseModel


class SourcesResponse(BaseModel):
    sources: list[str]
