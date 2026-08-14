from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app import __version__
from app.db.session import database_is_ready

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check: confirms that the API process can answer requests."""

    return {"status": "ok", "version": __version__}


@router.get("/ready")
def ready() -> dict[str, str]:
    """Readiness check: confirms that the API can connect to PostgreSQL."""

    if not database_is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready.",
        )
    return {"status": "ready", "database": "ok"}
