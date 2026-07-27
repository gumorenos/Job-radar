from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    root: Path
    database_url: str
    api_key: str
    allow_unauthenticated: bool
    profile_path: Path
    candidate_profile_path: Path
    log_level: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root = Path(__file__).resolve().parents[1]
    default_db = root / "tracking" / "job-radar" / "job_radar.sqlite"
    default_profile = root / "config" / "job-radar-profile.json"
    default_candidate = root / "tracking" / "job-radar" / "profile" / "candidate-profile.json"

    return Settings(
        root=root,
        database_url=os.getenv("JOB_RADAR_DATABASE_URL", f"sqlite:///{default_db}"),
        api_key=os.getenv("JOB_RADAR_API_KEY", "").strip(),
        allow_unauthenticated=_env_bool("JOB_RADAR_ALLOW_UNAUTHENTICATED", False),
        profile_path=Path(os.getenv("JOB_RADAR_PROFILE_PATH", str(default_profile))),
        candidate_profile_path=Path(os.getenv("JOB_RADAR_CANDIDATE_PROFILE_PATH", str(default_candidate))),
        log_level=os.getenv("JOB_RADAR_LOG_LEVEL", "INFO").upper(),
    )
