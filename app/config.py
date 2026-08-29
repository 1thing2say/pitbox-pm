"""Configuration. Every value has a working default so `uvicorn app.main:app` runs
with no setup at all; override any of them in a .env file (see .env.example)."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PITBOX_", env_file=".env", extra="ignore")

    team_name: str = "MESA ARC Racing"

    # sqlite:///./pitbox.db for a laptop or a small shop server.
    # postgresql+psycopg://user:pass@host/db when you outgrow it — nothing else changes.
    database_url: str = "sqlite:///./pitbox.db"

    storage_dir: Path = BASE_DIR / "storage"
    max_upload_mb: int = 100

    # Extensions we refuse outright. Everything else is allowed but is always
    # served back as an attachment, never executed or inlined.
    blocked_extensions: tuple[str, ...] = (
        ".exe", ".dll", ".bat", ".cmd", ".com", ".scr", ".msi", ".ps1", ".sh", ".jar",
    )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
