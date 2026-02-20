#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""
PyFoswiki Web UI — standalone FastAPI app.

Run:
    uvicorn webui.app:app --host 127.0.0.1 --port 8001 --reload

Or via Makefile:
    make start-web
    make start-web-bg
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import init_db
from webui.pages import acl, admin, attachments, auth, forms, groups, webs, topics, search, users
from webui.templating import templates


# -----------------------------------------------------------------------------

def create_webui() -> FastAPI:
    settings = get_settings()
    init_db()

    app = FastAPI(
        title=f"{settings.app_name} Web UI",
        version=settings.app_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # ── Static files ──────────────────────────────────────────────────────────

    _static = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(_static):
        app.mount("/static", StaticFiles(directory=_static), name="static")

    # ── Page routers ──────────────────────────────────────────────────────────

    app.include_router(auth.router)
    app.include_router(webs.router)
    app.include_router(topics.router)
    app.include_router(search.router)
    app.include_router(users.router)
    app.include_router(admin.router)
    app.include_router(forms.router)
    app.include_router(attachments.router)
    app.include_router(acl.router)
    app.include_router(groups.router)

    # ── Catch-all 404 ─────────────────────────────────────────────────────────

    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "ctx": None, "title": "Not Found",
             "user": None, "flash": None, "flash_type": "error",
             "message": "Page not found."},
            status_code=404,
        )

    return app


# -----------------------------------------------------------------------------

app = create_webui()


# -----------------------------------------------------------------------------
