"""Health check API endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    """Return the health status of the application."""
    return {"status": "ok"}
