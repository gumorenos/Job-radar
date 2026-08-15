from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import Classification, FeedbackReason
from app.db.models import ClassificationFeedback, Job, MatchAnalysis
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/radar/jobs", tags=["feedback"])
SessionDep = Annotated[Session, Depends(get_session)]


class ClassificationFeedbackRequest(BaseModel):
    human_classification: Classification
    reason_code: FeedbackReason
    comment: str | None = Field(default=None, max_length=2000)


class ClassificationFeedbackResponse(BaseModel):
    id: UUID
    job_id: UUID
    match_analysis_id: UUID
    system_classification: Classification
    human_classification: Classification
    reason_code: FeedbackReason
    comment: str | None
    created_at: datetime


def _latest_classified_analysis(session: Session, job_id: UUID) -> MatchAnalysis | None:
    return session.scalar(
        select(MatchAnalysis)
        .where(
            MatchAnalysis.job_id == job_id,
            MatchAnalysis.classification.is_not(None),
        )
        .order_by(MatchAnalysis.created_at.desc())
        .limit(1)
    )


@router.post(
    "/{job_id}/feedback",
    response_model=ClassificationFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_classification_feedback(
    job_id: UUID,
    payload: ClassificationFeedbackRequest,
    session: SessionDep,
) -> ClassificationFeedbackResponse:
    if session.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    analysis = _latest_classified_analysis(session, job_id)
    if analysis is None or analysis.classification is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The job needs a system classification before feedback can be recorded.",
        )

    feedback = ClassificationFeedback(
        match_analysis_id=analysis.id,
        job_id=job_id,
        system_classification=analysis.classification,
        human_classification=payload.human_classification,
        reason_code=payload.reason_code,
        comment=payload.comment.strip() if payload.comment and payload.comment.strip() else None,
    )
    session.add(feedback)
    session.commit()
    session.refresh(feedback)

    return ClassificationFeedbackResponse(
        id=feedback.id,
        job_id=feedback.job_id,
        match_analysis_id=feedback.match_analysis_id,
        system_classification=feedback.system_classification,
        human_classification=feedback.human_classification,
        reason_code=feedback.reason_code,
        comment=feedback.comment,
        created_at=feedback.created_at,
    )
