"""Health check and sources endpoints."""

from fastapi import APIRouter

from finbar.core.domain.entities.data_source import DataSource
from finbar.presentation.api.dto.responses import HealthResponse, SourcesResponse

router = APIRouter(prefix="/api", tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
)
def health():
    """Return service health status."""
    return HealthResponse(status="ok")


@router.get(
    "/sources",
    response_model=SourcesResponse,
    summary="List available data sources",
)
def list_sources():
    """Return available data sources."""
    return SourcesResponse(sources=[s.value for s in DataSource])
