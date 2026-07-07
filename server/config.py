"""Application settings loaded from environment variables (.env supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    db_path: str
    presave_url: str
    admin_user: str
    admin_pass: str
    secret_key: str
    public_base_url: str | None = None
    app_version: str = "dev"   # deploy tag (APP_VERSION, baked at build): cache-buster + shown in-page


def load_settings() -> Settings:
    """Build Settings from the process environment; loads a local .env if present."""
    load_dotenv()  # no-op if there is no .env file
    return Settings(
        db_path=os.getenv("DB_PATH") or "db/stats.db",
        presave_url=os.getenv("PRESAVE_URL", ""),
        admin_user=os.getenv("ADMIN_USER", "admin"),
        admin_pass=os.getenv("ADMIN_PASS", ""),
        secret_key=os.getenv("SECRET_KEY", "dev-insecure-key"),
        public_base_url=os.getenv("PUBLIC_BASE_URL") or None,
        app_version=os.getenv("APP_VERSION") or "dev",
    )
