from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

_bearer = HTTPBearer(auto_error=False)


def _require_bearer_secret(
    credentials: HTTPAuthorizationCredentials | None,
    *,
    expected: str,
    setting_name: str,
) -> None:
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{setting_name} is not configured.",
        )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    if not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
        )


def require_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> None:
    """Validate the general integration API key."""

    _require_bearer_secret(
        credentials,
        expected=get_settings().api_key.get_secret_value().strip(),
        setting_name="JOB_RADAR_API_KEY",
    )


def require_extension_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> None:
    """Validate the browser-extension-only API key."""

    _require_bearer_secret(
        credentials,
        expected=get_settings().extension_api_key.get_secret_value().strip(),
        setting_name="JOB_RADAR_EXTENSION_API_KEY",
    )
