#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
PyFoswiki — Phase 1 FastAPI Application
========================================
Entry point.  Start with:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import auth, attachments, search, topics, webs

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown."""
    # In production, Alembic handles migrations.
    # For dev / tests, we can auto-create tables here.
    if settings.debug:
        from app.core.database import init_db
        await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A Python wiki engine inspired by Foswiki",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────
API = "/api/v1"
app.include_router(auth.router,        prefix=API)
app.include_router(webs.router,        prefix=API)
app.include_router(topics.router,      prefix=API)
app.include_router(attachments.router, prefix=API)
app.include_router(search.router,      prefix=API)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/api/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}



