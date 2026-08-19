from __future__ import annotations

from enum import StrEnum


class Classification(StrEnum):
    HIGH_PRIORITY = "HIGH_PRIORITY"
    REVIEW = "REVIEW"
    DISCARD = "DISCARD"


class WorkMode(StrEnum):
    ONSITE = "ONSITE"
    HYBRID = "HYBRID"
    REMOTE = "REMOTE"
    UNKNOWN = "UNKNOWN"


class JobStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class PostingStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class IngestionStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskType(StrEnum):
    NORMALIZE_INGESTION = "NORMALIZE_INGESTION"
    ENRICH_POSTING = "ENRICH_POSTING"
    DEDUPLICATE_JOB = "DEDUPLICATE_JOB"
    ANALYZE_MATCH = "ANALYZE_MATCH"
    CLASSIFY_JOB = "CLASSIFY_JOB"
    SEND_NOTIFICATION = "SEND_NOTIFICATION"


class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FeedbackReason(StrEnum):
    SALARY = "SALARY"
    SENIORITY = "SENIORITY"
    SKILLS = "SKILLS"
    LOCATION = "LOCATION"
    INDUSTRY = "INDUSTRY"
    DEGREE = "DEGREE"
    TITLE = "TITLE"
    OTHER = "OTHER"


class ApplicationStage(StrEnum):
    TO_APPLY = "TO_APPLY"
    APPLIED = "APPLIED"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    CLOSED = "CLOSED"


class DuplicateCandidateStatus(StrEnum):
    PENDING = "PENDING"
    MERGED = "MERGED"
    KEPT_SEPARATE = "KEPT_SEPARATE"


class CvApprovalStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class NotificationChannel(StrEnum):
    TELEGRAM = "TELEGRAM"
    DASHBOARD = "DASHBOARD"


class NotificationType(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    DAILY_REVIEW = "DAILY_REVIEW"


class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
