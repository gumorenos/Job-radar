from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from JOB_RADAR_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="JOB_RADAR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = (
        "postgresql+psycopg://job_radar:job_radar_dev@localhost:5432/job_radar"
    )
    api_key: SecretStr = SecretStr("")
    log_level: str = "INFO"
    storage_path: Path = Path("./storage")
    worker_poll_interval_seconds: float = 2.0
    worker_stale_task_seconds: int = 900
    reappearance_window_days: int = 30
    telegram_enabled: bool = False
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
