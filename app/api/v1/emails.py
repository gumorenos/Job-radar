from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.session import get_session
from app.domains.email_ingestion.schemas import (
    EmailExtractionRequest,
    EmailExtractionResponse,
    InboundEmailAcceptance,
    InboundEmailList,
    InboundEmailRequest,
)
from app.domains.email_ingestion.service import (
    EmailExtractionConflictError,
    EmailIdempotencyConflictError,
    accept_inbound_email,
    list_inbound_emails,
    submit_email_extraction,
)

router = APIRouter(prefix="/api/v1/emails", tags=["emails"])
SessionDep = Annotated[Session, Depends(get_session)]
IdempotencyHeader = Annotated[
    str | None,
    Header(alias="Idempotency-Key", max_length=200),
]


@router.get("/inbound", response_model=InboundEmailList)
def inbound_email_list(
    session: SessionDep,
    provider: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=25, ge=1, le=100),
) -> InboundEmailList:
    return list_inbound_emails(session, provider=provider, limit=limit)


@router.post(
    "/inbound",
    response_model=InboundEmailAcceptance,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
async def receive_inbound_email(
    request: Request,
    payload: InboundEmailRequest,
    session: SessionDep,
    idempotency_key: IdempotencyHeader = None,
) -> InboundEmailAcceptance:
    raw_json: Any = await request.json()
    if not isinstance(raw_json, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The inbound email payload must be a JSON object.",
        )

    raw_payload: dict[str, object] = raw_json
    try:
        return accept_inbound_email(
            session,
            payload,
            idempotency_key,
            raw_payload=raw_payload,
        )
    except EmailIdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "/inbound/{email_id}/extractions",
    response_model=EmailExtractionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
def submit_inbound_email_extraction(
    email_id: UUID,
    payload: EmailExtractionRequest,
    session: SessionDep,
    idempotency_key: IdempotencyHeader = None,
) -> EmailExtractionResponse:
    try:
        return submit_email_extraction(session, email_id, payload, idempotency_key)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EmailExtractionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
