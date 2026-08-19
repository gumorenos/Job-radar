import pytest
from pydantic import SecretStr

from app.core.config import Settings


def test_production_rejects_default_api_key() -> None:
    settings = Settings(
        app_env="production",
        api_key=SecretStr("dev-only-change-me"),
        database_url="postgresql+psycopg://job_radar:secure@postgres:5432/job_radar",
    )

    with pytest.raises(RuntimeError, match="non-default JOB_RADAR_API_KEY"):
        settings.validate_runtime()


def test_production_rejects_development_database_password() -> None:
    settings = Settings(
        app_env="production",
        api_key=SecretStr("long-production-secret"),
        database_url="postgresql+psycopg://job_radar:job_radar_dev@postgres:5432/job_radar",
    )

    with pytest.raises(RuntimeError, match="development database password"):
        settings.validate_runtime()


def test_production_accepts_explicit_secrets() -> None:
    settings = Settings(
        app_env="production",
        api_key=SecretStr("long-production-secret"),
        database_url="postgresql+psycopg://job_radar:another-secret@postgres:5432/job_radar",
    )

    settings.validate_runtime()


def test_telegram_enabled_requires_complete_credentials() -> None:
    settings = Settings(
        telegram_enabled=True,
        telegram_bot_token=SecretStr(""),
        telegram_chat_id="",
    )

    with pytest.raises(RuntimeError, match="Telegram delivery is enabled"):
        settings.validate_runtime()
