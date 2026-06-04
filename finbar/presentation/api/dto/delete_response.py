"""Response for delete operations."""

from pydantic import BaseModel


class DeleteResponse(BaseModel):
    symbol: str
    deleted_count: int
