from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.applications import router as applications_router
from app.api.v1.cvs import router as cvs_router
from app.api.v1.duplicates import router as duplicates_router
from app.api.v1.emails import router as emails_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.feedback_insights import router as feedback_insights_router
from app.api.v1.health import router as health_router
from app.api.v1.ingestions import router as ingestion_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.profile import router as profile_router
from app.api.v1.radar import router as radar_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(ingestion_router)
api_router.include_router(emails_router)
api_router.include_router(radar_router)
api_router.include_router(duplicates_router)
api_router.include_router(feedback_router)
api_router.include_router(feedback_insights_router)
api_router.include_router(applications_router)
api_router.include_router(cvs_router)
api_router.include_router(profile_router)
api_router.include_router(notifications_router)
