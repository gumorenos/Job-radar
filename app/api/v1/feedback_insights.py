from __future__ import annotations

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import Classification, FeedbackReason
from app.db.models import ClassificationFeedback
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])
SessionDep = Annotated[Session, Depends(get_session)]


class FeedbackReasonCount(BaseModel):
    reason: FeedbackReason
    count: int
    overrides: int


class FeedbackTransitionCount(BaseModel):
    system_classification: Classification
    human_classification: Classification
    count: int


class FeedbackInsights(BaseModel):
    total_events: int
    jobs_with_feedback: int
    current_overrides: int
    current_agreements: int
    by_reason: list[FeedbackReasonCount]
    transitions: list[FeedbackTransitionCount]


def _latest_feedback_per_job(session: Session) -> list[ClassificationFeedback]:
    return list(
        session.scalars(
            select(ClassificationFeedback)
            .distinct(ClassificationFeedback.job_id)
            .order_by(
                ClassificationFeedback.job_id,
                ClassificationFeedback.created_at.desc(),
                ClassificationFeedback.id.desc(),
            )
        )
    )


@router.get("/insights", response_model=FeedbackInsights)
def feedback_insights(session: SessionDep) -> FeedbackInsights:
    total_events = int(
        session.scalar(select(func.count(ClassificationFeedback.id))) or 0
    )
    jobs_with_feedback = int(
        session.scalar(
            select(func.count(func.distinct(ClassificationFeedback.job_id)))
        )
        or 0
    )
    latest = _latest_feedback_per_job(session)

    current_overrides = sum(
        item.human_classification != item.system_classification for item in latest
    )
    current_agreements = len(latest) - current_overrides

    reason_counts: Counter[FeedbackReason] = Counter()
    reason_overrides: Counter[FeedbackReason] = Counter()
    transition_counts: Counter[tuple[Classification, Classification]] = Counter()
    for item in latest:
        reason_counts[item.reason_code] += 1
        is_override = item.human_classification != item.system_classification
        if is_override:
            reason_overrides[item.reason_code] += 1
        transition_counts[(item.system_classification, item.human_classification)] += 1

    by_reason = [
        FeedbackReasonCount(
            reason=reason,
            count=count,
            overrides=reason_overrides[reason],
        )
        for reason, count in sorted(
            reason_counts.items(),
            key=lambda item: (-item[1], item[0].value),
        )
    ]
    transitions = [
        FeedbackTransitionCount(
            system_classification=system_classification,
            human_classification=human_classification,
            count=count,
        )
        for (system_classification, human_classification), count in sorted(
            transition_counts.items(),
            key=lambda item: (-item[1], item[0][0].value, item[0][1].value),
        )
    ]

    return FeedbackInsights(
        total_events=total_events,
        jobs_with_feedback=jobs_with_feedback,
        current_overrides=current_overrides,
        current_agreements=current_agreements,
        by_reason=by_reason,
        transitions=transitions,
    )
