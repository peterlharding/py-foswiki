#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Application configuration loaded from environment variables / .env file.
"""

from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Application ────────────────────────────────────────────────────────
    app_name: str = "PyFoswiki"
    app_version: str = "0.1.0"
    debug: bool = False
    base_url: str = "http://localhost:8000"

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://pyfoswiki:pyfoswiki@localhost:5432/pyfoswiki"

    # ── Auth / JWT ─────────────────────────────────────────────────────────
    secret_key: str = "CHANGE-ME-IN-PRODUCTION-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8   # 8 hours

    # ── File storage ───────────────────────────────────────────────────────
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 50

    # ── Wiki defaults ──────────────────────────────────────────────────────
    default_web: str = "Main"
    site_name: str = "My PyFoswiki"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()



