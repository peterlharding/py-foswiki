#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""
Site administration pages.

GET  /admin/settings          — view site settings
POST /admin/settings          — update settings (writes to .env)
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.config import get_settings
from webui.context import PageContext
from webui.session import get_current_user
from webui.templating import templates

router = APIRouter(prefix="/admin", tags=["webui-admin"])

_ENV_FILE = Path(".env")


# ── helpers ───────────────────────────────────────────────────────────────────

async def _require_admin(request: Request):
    user = await get_current_user(request)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    if not user.get("is_admin"):
        ctx = PageContext(title="Forbidden", user=user)
        return None, templates.TemplateResponse("error.html", {
            **ctx.to_dict(request),
            "message": "Admin access required.",
        }, status_code=403)
    return user, None


def _read_env() -> dict[str, str]:
    """Read current .env file into a dict."""
    env: dict[str, str] = {}
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _write_env_key(key: str, value: str) -> None:
    """Set a single key in .env, creating the file if needed."""
    env = _read_env()
    env[key] = value
    lines = []
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k == key:
                    lines.append(f"{key}={value}")
                    continue
            lines.append(line)
        if key not in env or key not in [l.split("=")[0].strip() for l in _ENV_FILE.read_text().splitlines() if "=" in l]:
            lines.append(f"{key}={value}")
    else:
        lines.append(f"{key}={value}")
    _ENV_FILE.write_text("\n".join(lines) + "\n")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user, err = await _require_admin(request)
    if err:
        return err
    settings = get_settings()
    ctx = PageContext(title="Site Settings", user=user)
    return templates.TemplateResponse("admin/settings.html", {
        **ctx.to_dict(request),
        "settings": settings,
        "success": "",
    })


@router.post("/settings/toggle-registration")
async def toggle_registration(request: Request):
    user, err = await _require_admin(request)
    if err:
        return err
    current = get_settings().allow_registration
    _write_env_key("ALLOW_REGISTRATION", "false" if current else "true")
    # Bust the lru_cache so the new value is picked up immediately
    get_settings.cache_clear()
    return RedirectResponse(url="/admin/settings", status_code=302)
