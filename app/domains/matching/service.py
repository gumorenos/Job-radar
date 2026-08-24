from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import Classification, Confidence, CvApprovalStatus, TaskStatus, TaskType
from app.db.models import Company, CvVersion, Job, JobPosting, MatchAnalysis, ProcessingTask
from app.domains.jobs.normalization import comparison_key
from app.domains.matching.facts import (
    is_international_remote,
    monthly_salary_pen,
    published_salary_unassessed,
)
from app.domains.matching.fit import FitSignalInput, assess_career_move, evaluate_positive_fit
from app.domains.matching.rules import (
    MatchingRuleInput,
    MatchingRulePolicy,
    RuleResult,
    evaluate_business_rules,
)
from app.domains.notifications.service import plan_match_notifications
from app.domains.profiles.service import get_or_create_active_profile

ANALYZER_VERSION = "rules-v4"


def _latest_posting(session: Session, job_id: UUID) -> JobPosting | None:
    return session.scalar(
        select(JobPosting)
        .where(JobPosting.job_id == job_id)
        .order_by(JobPosting.last_seen_at.desc())
        .limit(1)
    )


def _company_industry(session: Session, job: Job) -> str | None:
    if job.company_id is None:
        return None
    company = session.get(Company, job.company_id)
    return company.industry if company is not None else None


def _rule_payload(evaluation_results: tuple[RuleResult, ...]) -> list[dict[str, object]]:
    return [
        {
            "code": item.code,
            "passed": item.passed,
            "severity": item.severity,
            "message": item.message,
        }
        for item in evaluation_results
    ]


def _cv_target_matches(cv: CvVersion, text_key: str) -> bool:
    targets = (cv.target_role, cv.target_area)
    for value in targets:
        key = comparison_key(value)
        if key and key in text_key:
            return True
    return False


def _recommended_cv(session: Session, profile_id: UUID, job: Job) -> CvVersion | None:
    cvs = list(
        session.scalars(
            select(CvVersion)
            .where(
                CvVersion.candidate_profile_id == profile_id,
                CvVersion.approval_status == CvApprovalStatus.APPROVED,
            )
            .order_by(CvVersion.is_active.desc(), CvVersion.version.desc())
        )
    )
    if not cvs:
        return None

    text_key = comparison_key(" ".join(filter(None, (job.canonical_title, job.description)))) or ""
    specialized = [cv for cv in cvs if not cv.is_base and _cv_target_matches(cv, text_key)]
    if specialized:
        return specialized[0]

    base = next((cv for cv in cvs if cv.is_base), None)
    if base is not None:
        return base
    return cvs[0]


def analyze_job(session: Session, job_id: UUID) -> MatchAnalysis:
    job = session.get(Job, job_id)
    if job is None:
        raise LookupError(f"Job {job_id} does not exist.")

    profile = get_or_create_active_profile(session)
    posting = _latest_posting(session, job.id)
    salary_pen = monthly_salary_pen(posting)
    local_floor = Decimal(profile.salary_min_pen)
    policy = MatchingRulePolicy(
        local_salary_min_pen=local_floor,
        remote_salary_min_pen=local_floor * Decimal(profile.remote_salary_multiplier),
    )
    facts = MatchingRuleInput(
        title=job.canonical_title,
        location=job.location_text,
        work_mode=job.work_mode,
        industry=_company_industry(session, job),
        monthly_salary_pen=salary_pen,
        salary_published_unassessed=published_salary_unassessed(posting),
        is_international_remote=is_international_remote(job),
    )
    evaluation = evaluate_business_rules(facts, policy)
    fit = evaluate_positive_fit(
        FitSignalInput(
            title=job.canonical_title,
            description=job.description,
            location=job.location_text,
            work_mode=job.work_mode,
            monthly_salary_pen=salary_pen,
            target_roles=tuple(profile.target_roles),
            target_areas=tuple(profile.target_areas),
            adjacent_areas=tuple(profile.adjacent_areas),
        )
    )

    if evaluation.forced_classification == Classification.DISCARD:
        classification = Classification.DISCARD
        confidence = Confidence.HIGH
        recommendation = "DESCARTAR"
    elif evaluation.requires_review:
        classification = Classification.REVIEW
        confidence = Confidence.MEDIUM
        recommendation = "REVISAR"
    elif fit.high_priority:
        classification = Classification.HIGH_PRIORITY
        confidence = Confidence.MEDIUM
        recommendation = "PRIORIZAR"
    else:
        classification = Classification.REVIEW
        confidence = Confidence.LOW
        recommendation = "REVISAR"

    rule_items = _rule_payload(evaluation.results)
    hard_messages = [item["message"] for item in rule_items if item["severity"] == "HARD"]
    warning_messages = [
        item["message"] for item in rule_items if item["severity"] == "WARNING"
    ]
    if hard_messages:
        explanation = " ".join(str(message) for message in hard_messages)
    elif warning_messages:
        explanation = " ".join(str(message) for message in warning_messages)
    elif classification == Classification.HIGH_PRIORITY:
        explanation = " ".join(fit.strengths[:2])
    else:
        explanation = (
            "No se activaron descartes, pero todavía falta una combinación fuerte de rol de "
            "RRHH/People y área foco para elevar la vacante a Alta prioridad."
        )

    salary_result = next(
        (item for item in rule_items if item["code"] == "PUBLISHED_SALARY"),
        None,
    )
    recommended_cv = _recommended_cv(session, profile.id, job)
    analysis = MatchAnalysis(
        job_id=job.id,
        candidate_profile_id=profile.id,
        cv_version_id=recommended_cv.id if recommended_cv is not None else None,
        overall_score=None,
        classification=classification,
        confidence=confidence,
        rule_results={
            "analyzer_version": ANALYZER_VERSION,
            "forced_classification": (
                evaluation.forced_classification.value
                if evaluation.forced_classification is not None
                else None
            ),
            "requires_review": evaluation.requires_review,
            "results": rule_items,
        },
        skill_analysis={
            "role_matches": list(fit.role_matches),
            "core_area_matches": list(fit.core_area_matches),
            "adjacent_area_matches": list(fit.adjacent_area_matches),
            "positive_fit_rule": "hr_role_and_core_area",
            "recommended_cv": (
                {
                    "id": str(recommended_cv.id),
                    "name": recommended_cv.name,
                    "version": recommended_cv.version,
                }
                if recommended_cv is not None
                else None
            ),
        },
        strengths=list(fit.strengths),
        gaps=[*warning_messages, *fit.gaps],
        career_move_assessment=assess_career_move(fit),
        salary_assessment=str(salary_result["message"]) if salary_result else None,
        recommendation=recommendation,
        explanation=explanation,
        analyzer_version=ANALYZER_VERSION,
    )
    session.add(analysis)
    session.flush()
    plan_match_notifications(session, analysis, profile)
    return analysis


def enqueue_job_analysis(session: Session, job_id: UUID) -> ProcessingTask:
    task = ProcessingTask(
        task_type=TaskType.ANALYZE_MATCH,
        entity_type="job",
        entity_id=job_id,
        status=TaskStatus.PENDING,
        priority=200,
    )
    session.add(task)
    session.flush()
    return task
