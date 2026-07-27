from __future__ import annotations

import hmac

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from job_radar_app.settings import get_settings


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(provided_key: str | None = Security(_api_key_header)) -> None:
    settings = get_settings()
    if settings.allow_unauthenticated:
        return
    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JOB_RADAR_API_KEY is not configured.",
        )
    if not provided_key or not hmac.compare_digest(provided_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
