"""Persistence model registry used by SQLAlchemy and Alembic."""

from app.db.models.applications import JobApplication
from app.db.models.duplicates import DuplicateCandidate
from app.db.models.emails import (
    EmailAttachment,
    EmailExtractedPosting,
    EmailProcessingRun,
    InboundEmail,
)
from app.db.models.evidence import CareerEvidence
from app.db.models.ingestion import IngestionEvent, ProcessingTask
from app.db.models.jobs import Company, Job, JobPosting, PostingSighting
from app.db.models.matching import ClassificationFeedback, MatchAnalysis
from app.db.models.notifications import Notification
from app.db.models.profiles import CandidateProfile, CvVersion

__all__ = [
    "CandidateProfile",
    "CareerEvidence",
    "ClassificationFeedback",
    "Company",
    "CvVersion",
    "DuplicateCandidate",
    "EmailAttachment",
    "EmailExtractedPosting",
    "EmailProcessingRun",
    "InboundEmail",
    "IngestionEvent",
    "Job",
    "JobApplication",
    "JobPosting",
    "MatchAnalysis",
    "Notification",
    "PostingSighting",
    "ProcessingTask",
]
