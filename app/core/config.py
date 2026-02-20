#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Application configuration.

All values can be overridden via environment variables or a .env file.
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


# -----------------------------------------------------------------------------

class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────

    app_name: str = "PyFoswiki"
    app_version: str = "0.5.0"
    base_url: str = "http://localhost:8621"
    debug: bool = False
    environment: Literal["development", "testing", "production"] = "development"

    # ── Database ───────────────────────────────────────────────────────────

    database_url: str = "postgresql+asyncpg://pyfoswiki:pyfoswiki@localhost:5432/pyfoswiki"
    # For tests, override to: "sqlite+aiosqlite:///./test.db"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # ── Auth / JWT ─────────────────────────────────────────────────────────

    secret_key: str = "CHANGE-ME-IN-PRODUCTION-use-a-random-64-char-hex-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8   # 8 hours
    refresh_token_expire_days: int = 30

    # ── Storage ────────────────────────────────────────────────────────────

    attachment_root: Path = Path("./data/attachments")
    max_attachment_bytes: int = 50 * 1024 * 1024   # 50 MB

    # ── Wiki defaults ──────────────────────────────────────────────────────

    default_web: str = "Main"
    site_name: str = "PyFoswiki"
    admin_email: str = "admin@example.com"
    allow_registration: bool = True   # set False to restrict account creation to admins only

    # ── CORS ───────────────────────────────────────────────────────────────

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8121",
        "https://py-foswiki.performiq.com",
    ]

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

    @property
    def attachment_root_resolved(self) -> Path:
        p = self.attachment_root
        p.mkdir(parents=True, exist_ok=True)
        return p


# -----------------------------------------------------------------------------

@lru_cache
def get_settings() -> Settings:
    return Settings()


# -----------------------------------------------------------------------------

