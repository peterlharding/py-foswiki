#!/usr/bin/env python
# -----------------------------------------------------------------------------
"""
Admin router  — Phase 6
=======================
All endpoints require the caller to be an authenticated admin.

GET    /api/v1/admin/stats                   — site statistics
GET    /api/v1/admin/config                  — read live settings
PUT    /api/v1/admin/config                  — update overridable settings
GET    /api/v1/admin/users                   — list / search users
GET    /api/v1/admin/users/{username}        — get single user
PATCH  /api/v1/admin/users/{username}/activate
PATCH  /api/v1/admin/users/{username}/deactivate
DELETE /api/v1/admin/users/{username}        — delete user
GET    /api/v1/admin/plugins                 — list loaded plugins
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models import Topic, TopicVersion, User, Web
from app.schemas import (
    AdminConfigResponse, AdminConfigUpdate, AdminStatsResponse,
    OKResponse, PluginInfo, UserAdminResponse,
)
from app.services import users as user_svc
from app.services.plugins import get_plugin_manager


# -----------------------------------------------------------------------------

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Auth guard ────────────────────────────────────────────────────────────────

async def _require_admin(
    caller_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> User:
    caller = await user_svc.get_user_by_id(db, caller_id)
    if not caller.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return caller


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Statistics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(
    _admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    user_count  = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    web_count   = (await db.execute(select(func.count()).select_from(Web))).scalar_one()
    topic_count = (await db.execute(select(func.count()).select_from(Topic))).scalar_one()
    version_count = (await db.execute(select(func.count()).select_from(TopicVersion))).scalar_one()
    admin_count = (await db.execute(
        select(func.count()).select_from(User).where(User.is_admin == True)
    )).scalar_one()
    inactive_count = (await db.execute(
        select(func.count()).select_from(User).where(User.is_active == False)
    )).scalar_one()

    return AdminStatsResponse(
        user_count=user_count,
        admin_count=admin_count,
        inactive_user_count=inactive_count,
        web_count=web_count,
        topic_count=topic_count,
        version_count=version_count,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Site config
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# In-process mutable overrides (reset on restart; a DB-backed config table
# would be the production approach, but this is sufficient for Phase 6).
_config_overrides: dict = {}


@router.get("/config", response_model=AdminConfigResponse)
async def get_config(_admin: User = Depends(_require_admin)):
    settings = get_settings()
    return AdminConfigResponse(
        site_name=_config_overrides.get("site_name", settings.site_name),
        base_url=_config_overrides.get("base_url", settings.base_url),
        allow_registration=_config_overrides.get(
            "allow_registration", settings.allow_registration
        ),
        default_web=_config_overrides.get("default_web", settings.default_web),
        admin_email=_config_overrides.get("admin_email", settings.admin_email),
        app_version=settings.app_version,
        environment=settings.environment,
    )


@router.put("/config", response_model=AdminConfigResponse)
async def update_config(
    data: AdminConfigUpdate,
    _admin: User = Depends(_require_admin),
):
    if data.site_name is not None:
        _config_overrides["site_name"] = data.site_name
    if data.allow_registration is not None:
        _config_overrides["allow_registration"] = data.allow_registration
    if data.default_web is not None:
        _config_overrides["default_web"] = data.default_web
    if data.admin_email is not None:
        _config_overrides["admin_email"] = data.admin_email

    settings = get_settings()
    return AdminConfigResponse(
        site_name=_config_overrides.get("site_name", settings.site_name),
        base_url=_config_overrides.get("base_url", settings.base_url),
        allow_registration=_config_overrides.get(
            "allow_registration", settings.allow_registration
        ),
        default_web=_config_overrides.get("default_web", settings.default_web),
        admin_email=_config_overrides.get("admin_email", settings.admin_email),
        app_version=settings.app_version,
        environment=settings.environment,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# User management
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _user_admin_response(user: User) -> UserAdminResponse:
    return UserAdminResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        wiki_name=user.wiki_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        groups=user.groups_list(),
        created_at=user.created_at,
    )


@router.get("/users", response_model=list[UserAdminResponse])
async def list_users(
    skip:   int = Query(0, ge=0),
    limit:  int = Query(50, ge=1, le=200),
    search: str | None = Query(None, max_length=128),
    _admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).order_by(User.username).offset(skip).limit(limit)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            User.username.ilike(pattern) | User.email.ilike(pattern) |
            User.display_name.ilike(pattern)
        )
    result = await db.execute(stmt)
    return [_user_admin_response(u) for u in result.scalars().all()]


@router.get("/users/{username}", response_model=UserAdminResponse)
async def get_user(
    username: str,
    _admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await user_svc.get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    return _user_admin_response(user)


@router.patch("/users/{username}/activate", response_model=UserAdminResponse)
async def activate_user(
    username: str,
    _admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await user_svc.set_active(db, username, is_active=True)
    return _user_admin_response(user)


@router.patch("/users/{username}/deactivate", response_model=UserAdminResponse)
async def deactivate_user(
    username: str,
    _admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await user_svc.set_active(db, username, is_active=False)
    return _user_admin_response(user)


@router.delete("/users/{username}", response_model=OKResponse)
async def delete_user(
    username: str,
    caller: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    if username == caller.username:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    await user_svc.delete_user(db, username)
    return OKResponse(message=f"User '{username}' deleted")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Plugin management
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/plugins", response_model=list[PluginInfo])
async def list_plugins(_admin: User = Depends(_require_admin)):
    mgr = get_plugin_manager()
    return [
        PluginInfo(name=p.name, enabled=p.enabled, plugin_class=type(p).__name__)
        for p in mgr.plugins
    ]
