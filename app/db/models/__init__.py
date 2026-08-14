"""Persistence model registry used by SQLAlchemy and Alembic."""

from app.db.models.ingestion import IngestionEvent, ProcessingTask
from app.db.models.jobs import Company, Job, JobPosting, PostingSighting
from app.db.models.matching import ClassificationFeedback, MatchAnalysis
from app.db.models.notifications import Notification
from app.db.models.profiles import CandidateProfile, CvVersion

__all__ = [
    "CandidateProfile",
    "ClassificationFeedback",
    "Company",
    "CvVersion",
    "IngestionEvent",
    "Job",
    "JobPosting",
    "MatchAnalysis",
    "Notification",
    "PostingSighting",
    "ProcessingTask",
]
