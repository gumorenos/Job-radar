from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from job_radar_app.database import Base


class Vacancy(Base):
    __tablename__ = "vacancies"
    __table_args__ = (
        Index("vacancies_score_idx", "status", "score", "last_seen_at"),
        Index("vacancies_source_idx", "source"),
        Index("vacancies_duplicate_key_idx", "duplicate_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    external_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_detail: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    remote: Mapped[str | None] = mapped_column(Text)
    published: Mapped[str | None] = mapped_column(Text)
    salary_text: Mapped[str | None] = mapped_column(Text)
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_currency: Mapped[str | None] = mapped_column(String(20))
    url: Mapped[str | None] = mapped_column(Text)
    clean_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="new")
    first_seen_at: Mapped[str] = mapped_column(String, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(String, nullable=False)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    duplicate_key: Mapped[str | None] = mapped_column(Text)
    duplicate_of: Mapped[str | None] = mapped_column(String, ForeignKey("vacancies.id"))


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String)
    profile_name: Mapped[str | None] = mapped_column(Text)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    blockers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    duplicate_groups: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_hidden: Mapped[int] = mapped_column(Integer, default=0)


class VacancyAnalysis(Base):
    __tablename__ = "vacancy_analyses"
    __table_args__ = (
        Index("vacancy_analyses_vacancy_idx", "vacancy_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    vacancy_id: Mapped[str] = mapped_column(String, ForeignKey("vacancies.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    match_score: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    analysis_json: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        UniqueConstraint("source", "source_run_id", name="uq_ingestion_runs_source_run"),
        Index("ingestion_runs_finished_idx", "finished_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_run_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String)
    received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_relevant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    result_json: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
