from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.session import get_session
from app.domains.ingestion.schemas import JobIngestionRequest, JobIngestionResponse
from app.domains.ingestion.service import IdempotencyConflictError, accept_job_ingestion

router = APIRouter(prefix="/api/v1/ingestions", tags=["ingestion"])


@router.post(
    "/jobs",
    response_model=JobIngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
async def ingest_job(
    request: Request,
    payload: JobIngestionRequest,
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JobIngestionResponse:
    # Preserve the complete semantic JSON document received from the integration, including
    # fields that the current normalized request schema does not yet understand.
    raw_json: Any = await request.json()
    if not isinstance(raw_json, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The ingestion payload must be a JSON object.",
        )

    try:
        result = accept_job_ingestion(
            session,
            payload,
            idempotency_key,
            raw_payload=raw_json,
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return JobIngestionResponse(
        ingestion_id=result.ingestion_id,
        status=result.status,
        received_at=result.received_at,
    )
