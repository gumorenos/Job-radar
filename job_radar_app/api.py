from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from job_radar_app import __version__
from job_radar_app.database import get_engine, get_session, init_database
from job_radar_app.models import Vacancy
from job_radar_app.schemas import HealthResponse, IngestionBatchIn, IngestionResult, JobSummary
from job_radar_app.security import require_api_key
from job_radar_app.services.ingestion import ingest_batch


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(
    title="Job Radar Personal API",
    version=__version__,
    description="API común para OpenClaw, MCP, automatizaciones y futuras extensiones de navegador.",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        database=get_engine().dialect.name,
        version=__version__,
    )


@app.post(
    "/api/v1/postings/ingest",
    response_model=IngestionResult,
    dependencies=[Depends(require_api_key)],
    tags=["ingestion"],
)
def ingest_postings(batch: IngestionBatchIn, session: Session = Depends(get_session)) -> dict:
    """Ingest a batch once; retries with the same source/source_run_id replay the saved result."""
    return ingest_batch(session, batch)


@app.get(
    "/api/v1/jobs",
    response_model=list[JobSummary],
    dependencies=[Depends(require_api_key)],
    tags=["jobs"],
)
def list_jobs(
    session: Session = Depends(get_session),
    status: str = Query("active"),
    verdict: str | None = Query(None),
    q: str | None = Query(None, max_length=200),
    since: str | None = Query(None, description="ISO timestamp compared against first_seen_at"),
    limit: int = Query(100, ge=1, le=500),
) -> list[JobSummary]:
    statement = select(Vacancy)
    if status == "active":
        statement = statement.where(
            Vacancy.status.notin_({"discarded", "duplicate", "false_positive"})
        )
    elif status:
        statement = statement.where(Vacancy.status == status)
    if verdict:
        statement = statement.where(Vacancy.verdict == verdict)
    if since:
        statement = statement.where(Vacancy.first_seen_at >= since)
    if q:
        pattern = f"%{q.strip().lower()}%"
        statement = statement.where(
            or_(
                Vacancy.title.ilike(pattern),
                Vacancy.company.ilike(pattern),
                Vacancy.location.ilike(pattern),
                Vacancy.description.ilike(pattern),
            )
        )
    statement = statement.order_by(Vacancy.score.desc(), Vacancy.last_seen_at.desc()).limit(limit)
    rows = session.scalars(statement).all()
    return [
        JobSummary(
            id=row.id,
            source=row.source,
            title=row.title,
            company=row.company,
            location=row.location,
            remote=row.remote,
            published=row.published,
            salary_text=row.salary_text,
            url=row.url,
            score=row.score,
            verdict=row.verdict,
            status=row.status,
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at,
        )
        for row in rows
    ]


@app.get(
    "/api/v1/jobs/new-relevant",
    response_model=list[JobSummary],
    dependencies=[Depends(require_api_key)],
    tags=["jobs"],
)
def list_new_relevant_jobs(
    session: Session = Depends(get_session),
    since: str | None = Query(None, description="ISO timestamp compared against first_seen_at"),
    limit: int = Query(100, ge=1, le=500),
) -> list[JobSummary]:
    statement = select(Vacancy).where(
        Vacancy.verdict.in_({"priorizar", "revisar"}),
        Vacancy.status.notin_({"duplicate", "discarded", "false_positive"}),
    )
    if since:
        statement = statement.where(Vacancy.first_seen_at >= since)
    statement = statement.order_by(Vacancy.first_seen_at.desc(), Vacancy.score.desc()).limit(limit)
    rows = session.scalars(statement).all()
    return [
        JobSummary(
            id=row.id,
            source=row.source,
            title=row.title,
            company=row.company,
            location=row.location,
            remote=row.remote,
            published=row.published,
            salary_text=row.salary_text,
            url=row.url,
            score=row.score,
            verdict=row.verdict,
            status=row.status,
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at,
        )
        for row in rows
    ]
