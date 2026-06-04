"""Health check endpoint."""

from fastapi import APIRouter

from finbar.presentation.api.dto.responses import HealthResponse

router = APIRouter(prefix="/api", tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
)
def health():
    """Return service health status."""
    return HealthResponse(status="ok")
