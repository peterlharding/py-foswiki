#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Topics router
=============
GET    /api/v1/webs/{web}/topics                     — list topics
POST   /api/v1/webs/{web}/topics                     — create topic     [auth]
GET    /api/v1/webs/{web}/topics/{topic}             — get latest (rendered)
GET    /api/v1/webs/{web}/topics/{topic}/raw         — get raw content
GET    /api/v1/webs/{web}/topics/{topic}/history     — version list
GET    /api/v1/webs/{web}/topics/{topic}/diff/{a}/{b}— diff two versions
PUT    /api/v1/webs/{web}/topics/{topic}             — save new version  [auth]
POST   /api/v1/webs/{web}/topics/{topic}/rename      — rename topic      [auth]
DELETE /api/v1/webs/{web}/topics/{topic}             — delete topic      [auth]
GET    /api/v1/webs/{web}/topics/{topic}/acl         — get ACL
PUT    /api/v1/webs/{web}/topics/{topic}/acl         — set ACL           [auth]
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id, get_optional_user_id
from app.schemas import (
    ACLResponse, ACLUpdate, DiffResponse, OKResponse,
    TopicCreate, TopicRename, TopicResponse, TopicSummary, TopicUpdate,
    TopicVersionResponse,
)
from app.services import acl as acl_svc
from app.services import topics as topic_svc
from app.services import webs as web_svc
from app.services.users import get_user_by_id
from app.services.renderer import RenderPipeline
from app.core.config import get_settings


# -----------------------------------------------------------------------------

router = APIRouter(prefix="/webs/{web_name}/topics", tags=["topics"])


# -----------------------------------------------------------------------------

def _get_pipeline(db) -> RenderPipeline:
    settings = get_settings()
    return RenderPipeline(base_url=settings.base_url, db=db)


# ── List ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[TopicSummary])
async def list_topics(
    web_name: str,
    skip: int  = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None, max_length=128),
    db: AsyncSession = Depends(get_db),
):
    return await topic_svc.list_topics(db, web_name, skip=skip, limit=limit, search=search)


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("", response_model=TopicResponse, status_code=201)
async def create_topic(
    web_name: str,
    data: TopicCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    topic, ver = await topic_svc.create_topic(db, web_name, data, author_id=user_id)
    user = await get_user_by_id(db, user_id)
    pipeline = _get_pipeline(db)
    rendered = await pipeline.render(web_name, topic.name, ver.content, current_user=user.to_dict())
    return await _topic_response(db, web_name, topic, ver, rendered)


# ── Read ──────────────────────────────────────────────────────────────────────

@router.get("/{topic_name}", response_model=TopicResponse)
async def get_topic(
    web_name: str,
    topic_name: str,
    version: Optional[int] = Query(None, ge=1),
    render: bool = Query(True),
    user_id: Optional[str] = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
):
    topic, ver = await topic_svc.get_topic(db, web_name, topic_name, version=version)

    current_user = None
    if user_id:
        u = await get_user_by_id(db, user_id)
        current_user = u.to_dict()

    rendered = None
    if render:
        # Use cached rendered HTML if available and no specific version requested
        if ver.rendered and version is None:
            rendered = ver.rendered
        else:
            pipeline = _get_pipeline(db)
            rendered = await pipeline.render(web_name, topic_name, ver.content, current_user=current_user)
            if version is None:
                ver.rendered = rendered   # cache it

    return await _topic_response(db, web_name, topic, ver, rendered)


@router.get("/{topic_name}/raw")
async def get_topic_raw(
    web_name: str,
    topic_name: str,
    version: Optional[int] = Query(None, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """Return raw TML/Markdown source as plain text."""
    _topic, ver = await topic_svc.get_topic(db, web_name, topic_name, version=version)
    return Response(content=ver.content, media_type="text/plain")


# ── History ───────────────────────────────────────────────────────────────────

@router.get("/{topic_name}/history", response_model=list[TopicVersionResponse])
async def get_history(
    web_name: str,
    topic_name: str,
    db: AsyncSession = Depends(get_db),
):
    versions = await topic_svc.get_topic_history(db, web_name, topic_name)
    return [_ver_response(v) for v in versions]


# ── Diff ──────────────────────────────────────────────────────────────────────

@router.get("/{topic_name}/diff/{from_ver}/{to_ver}", response_model=DiffResponse)
async def get_diff(
    web_name: str,
    topic_name: str,
    from_ver: int,
    to_ver: int,
    db: AsyncSession = Depends(get_db),
):
    diff = await topic_svc.get_diff(db, web_name, topic_name, from_ver, to_ver)
    return DiffResponse(
        web=web_name,
        topic=topic_name,
        from_version=from_ver,
        to_version=to_ver,
        diff=diff,
    )


# ── Update ────────────────────────────────────────────────────────────────────

@router.put("/{topic_name}", response_model=TopicResponse)
async def update_topic(
    web_name: str,
    topic_name: str,
    data: TopicUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    topic, ver = await topic_svc.update_topic(db, web_name, topic_name, data, author_id=user_id)
    user = await get_user_by_id(db, user_id)
    pipeline = _get_pipeline(db)
    rendered = await pipeline.render(web_name, topic_name, ver.content, current_user=user.to_dict())
    ver.rendered = rendered
    return await _topic_response(db, web_name, topic, ver, rendered)


# ── Rename ────────────────────────────────────────────────────────────────────

@router.post("/{topic_name}/rename", response_model=OKResponse)
async def rename_topic(
    web_name: str,
    topic_name: str,
    data: TopicRename,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await topic_svc.rename_topic(db, web_name, topic_name, data, author_id=user_id)
    return OKResponse(message=f"Topic renamed to '{data.new_name}'")


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{topic_name}", response_model=OKResponse)
async def delete_topic(
    web_name: str,
    topic_name: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await topic_svc.delete_topic(db, web_name, topic_name)
    return OKResponse(message=f"Topic '{topic_name}' deleted")


# ── ACL ───────────────────────────────────────────────────────────────────────

@router.get("/{topic_name}/acl", response_model=ACLResponse)
async def get_topic_acl(
    web_name: str,
    topic_name: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    topic, _ver = await topic_svc.get_topic(db, web_name, topic_name)
    entries = await acl_svc.get_acl(db, "topic", topic.id)
    return ACLResponse(
        resource_type="topic",
        resource_id=topic.id,
        entries=[{"principal": e.principal, "permission": e.permission, "allow": e.allow} for e in entries],
    )


# -----------------------------------------------------------------------------

@router.put("/{topic_name}/acl", response_model=ACLResponse)
async def set_topic_acl(
    web_name: str,
    topic_name: str,
    data: ACLUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    topic, _ver = await topic_svc.get_topic(db, web_name, topic_name)
    entries = await acl_svc.set_acl(db, "topic", topic.id, data)
    return ACLResponse(
        resource_type="topic",
        resource_id=topic.id,
        entries=[{"principal": e.principal, "permission": e.permission, "allow": e.allow} for e in entries],
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Response builders
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _topic_response(db, web_name, topic, ver, rendered) -> dict:
    meta = {m.key: m.value for m in topic.meta}
    return {
        "id":             topic.id,
        "web":            web_name,
        "name":           topic.name,
        "version":        ver.version,
        "content":        ver.content,
        "rendered":       rendered,
        "author_id":      ver.author_id,
        "author_username":ver.author.username if ver.author else None,
        "comment":        ver.comment,
        "meta":           meta,
        "created_at":     topic.created_at,
        "updated_at":     ver.created_at,
    }


# -----------------------------------------------------------------------------

def _ver_response(ver) -> dict:
    return {
        "id":             ver.id,
        "version":        ver.version,
        "content":        ver.content,
        "author_id":      ver.author_id,
        "author_username":ver.author.username if ver.author else None,
        "comment":        ver.comment,
        "created_at":     ver.created_at,
    }


# -----------------------------------------------------------------------------

