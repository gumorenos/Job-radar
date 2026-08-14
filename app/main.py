from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app import __version__
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Job Radar API",
    version=__version__,
    description="Personal job search intelligence and CRM backend.",
    lifespan=lifespan,
)
app.include_router(api_router)
