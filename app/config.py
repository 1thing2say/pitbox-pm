"""Configuration. Every value has a working default so `uvicorn app.main:app` runs
with no setup at all; override any of them in a .env file (see .env.example)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

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

    # --- who is allowed in ---------------------------------------------------
    # cloudflare : Cloudflare Access decides. The app trusts the identity in the
    #              Cf-Access-Authenticated-User-Email header and creates a member
    #              record the first time it sees someone. No passwords, no
    #              accounts to create, nothing to hand over but the dashboard.
    #              REQUIRES the app to be reachable ONLY through the tunnel.
    # password   : the built-in login (scrypt + sessions). For running without
    #              Cloudflare — a shop PC, a campus VM behind a VPN.
    # none       : wide open. Local development only.
    #
    # Defaults to cloudflare so a careless deploy fails closed rather than open.
    # dev.ps1 sets `none` explicitly, because that is what it is for.
    auth_mode: Literal["cloudflare", "password", "none"] = "cloudflare"

    # Cloudflare injects this once an Access policy is in front. Only trustworthy
    # because cloudflared is the sole route to the app; see docs/CLOUDFLARE.md.
    access_email_header: str = "Cf-Access-Authenticated-User-Email"

    session_days: int = 30

    # Set PITBOX_COOKIE_SECURE=true once you are behind HTTPS, so the session
    # cookie is never sent over a plain connection. Left false by default
    # because on http://localhost a secure cookie is simply dropped, and a login
    # that silently fails to stick is a miserable thing to debug.
    cookie_secure: bool = False

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
