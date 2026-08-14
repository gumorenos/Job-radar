from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import Classification, Confidence
from app.db.models import CandidateProfile, Company, Job, JobPosting, MatchAnalysis, ProcessingTask
from app.db.enums import TaskStatus, TaskType
from app.domains.matching.facts import is_international_remote, monthly_salary_pen
from app.domains.matching.rules import MatchingRuleInput, MatchingRulePolicy, evaluate_business_rules

ANALYZER_VERSION = "rules-v1"


def _active_profile(session: Session) -> CandidateProfile:
    profile = session.scalar(
        select(CandidateProfile)
        .where(CandidateProfile.is_active.is_(True))
        .order_by(CandidateProfile.created_at.asc())
        .limit(1)
    )
    if profile is not None:
        return profile

    profile = CandidateProfile(
        name="Perfil personal",
        is_active=True,
        salary_min_pen=Decimal("7000"),
        remote_salary_multiplier=Decimal("1.10"),
        target_locations=["Lima Metropolitana", "Remote LATAM", "Remote Global"],
        target_roles=[
            "Senior Analyst",
            "Senior Specialist",
            "Coordinator",
            "Supervisor",
            "HR Business Partner",
            "Senior HRBP",
            "Lead",
            "Manager",
            "Gerente",
        ],
        target_areas=[
            "Onboarding",
            "People Analytics",
            "Gestión Humana",
            "Compensaciones",
            "Relaciones Laborales",
            "HR Analytics",
        ],
        adjacent_areas=[
            "People Operations",
            "HR Operations",
            "Talent Management",
            "Organizational Development",
            "Workforce Analytics",
            "HR Transformation",
            "Employee Experience",
            "Total Rewards",
            "HRIS",
        ],
        rules={"source": "phase-0-confirmed-rules"},
    )
    session.add(profile)
    session.flush()
    return profile


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


def _rule_payload(evaluation_results: tuple[object, ...]) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for item in evaluation_results:
        code = getattr(item, "code")
        passed = getattr(item, "passed")
        severity = getattr(item, "severity")
        message = getattr(item, "message")
        payload.append(
            {
                "code": str(code),
                "passed": bool(passed),
                "severity": str(severity),
                "message": str(message),
            }
        )
    return payload


def analyze_job(session: Session, job_id: UUID) -> MatchAnalysis:
    job = session.get(Job, job_id)
    if job is None:
        raise LookupError(f"Job {job_id} does not exist.")

    profile = _active_profile(session)
    posting = _latest_posting(session, job.id)
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
        monthly_salary_pen=monthly_salary_pen(posting),
        is_international_remote=is_international_remote(job),
    )
    evaluation = evaluate_business_rules(facts, policy)

    classification = evaluation.forced_classification or Classification.REVIEW
    if classification == Classification.DISCARD:
        confidence = Confidence.HIGH
        recommendation = "DESCARTAR"
    elif evaluation.requires_review:
        confidence = Confidence.MEDIUM
        recommendation = "REVISAR"
    else:
        confidence = Confidence.LOW
        recommendation = "REVISAR"

    rule_items = _rule_payload(evaluation.results)
    hard_messages = [item["message"] for item in rule_items if item["severity"] == "HARD"]
    warning_messages = [item["message"] for item in rule_items if item["severity"] == "WARNING"]
    if hard_messages:
        explanation = " ".join(str(message) for message in hard_messages)
    elif warning_messages:
        explanation = " ".join(str(message) for message in warning_messages)
    else:
        explanation = (
            "No se activaron reglas de descarte. La vacante queda en revisión hasta completar "
            "la evaluación de ajuste y priorización."
        )

    salary_result = next(
        (item for item in rule_items if item["code"] == "PUBLISHED_SALARY"),
        None,
    )
    analysis = MatchAnalysis(
        job_id=job.id,
        candidate_profile_id=profile.id,
        cv_version_id=None,
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
        skill_analysis={},
        strengths=[],
        gaps=warning_messages,
        career_move_assessment=None,
        salary_assessment=str(salary_result["message"]) if salary_result else None,
        recommendation=recommendation,
        explanation=explanation,
        analyzer_version=ANALYZER_VERSION,
    )
    session.add(analysis)
    session.flush()
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
