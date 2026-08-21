from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging

WEB_DIR = Path(__file__).resolve().parent / "web"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.validate_runtime()
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
app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")
