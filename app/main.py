#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
PyFoswiki — FastAPI application factory
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


# -----------------------------------------------------------------------------

from app.core.config import get_settings
from app.core.database import create_all_tables, init_db
from app.routes import auth, topics, webs, attachments, search, forms, feeds, admin


# -----------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    settings = get_settings()
    init_db()
    if settings.is_testing or settings.debug:
        await create_all_tables()
    yield
    # Cleanup (nothing required yet)


# -----------------------------------------------------------------------------

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Python reimplementation of the Foswiki enterprise wiki platform.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────

    prefix = "/api/v1"

    app.include_router(auth.router,         prefix=prefix)
    app.include_router(webs.router,         prefix=prefix)
    app.include_router(topics.router,       prefix=prefix)
    app.include_router(attachments.router,  prefix=prefix)
    app.include_router(search.router,        prefix=prefix)
    app.include_router(forms.router,         prefix=prefix)
    app.include_router(feeds.router,         prefix=prefix)
    app.include_router(admin.router,         prefix=prefix)

    # ── Global exception handlers ─────────────────────────────────────────────

    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Not found"},
        )

    @app.exception_handler(500)
    async def server_error(request: Request, exc):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/api/health", tags=["system"])
    async def health():
        return {"status": "ok", "version": settings.app_version}

    return app


# -----------------------------------------------------------------------------

# Entrypoint for `uvicorn app.main:app`
app = create_app()


