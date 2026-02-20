#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Topics router
=============
GET    /api/v1/webs/{web}/topics                         — list topics
POST   /api/v1/webs/{web}/topics                         — create topic
GET    /api/v1/webs/{web}/topics/{topic}                 — get rendered topic
GET    /api/v1/webs/{web}/topics/{topic}/raw             — get raw source
PUT    /api/v1/webs/{web}/topics/{topic}                 — save new version
DELETE /api/v1/webs/{web}/topics/{topic}                 — delete topic
GET    /api/v1/webs/{web}/topics/{topic}/history         — version list
GET    /api/v1/webs/{web}/topics/{topic}/history/{ver}   — specific version
GET    /api/v1/webs/{web}/topics/{topic}/diff/{v1}/{v2}  — unified diff
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.models.user import User
from app.schemas import (
    DiffOut, TopicCreate, TopicListItem, TopicOut,
    TopicSave, VersionOut,
)
from app.services.topic_service import (
    TopicNameConflict,
    TopicNotFound,
    create_topic,
    delete_topic,
    diff_versions,
    get_history,
    get_topic,
    get_version,
    list_topics,
    save_topic,
)
from app.services.web_service import WebNotFound

router = APIRouter(prefix="/webs/{web_name}/topics", tags=["Topics"])


def _not_found(e: Exception):
    raise HTTPException(status_code=404, detail=str(e))


# ── List ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[TopicListItem])
async def list_topics_endpoint(
    web_name: str,
    search: Optional[str] = Query(default=None, description="Filter by topic name"),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_topics(db, web_name, search=search)
    except WebNotFound as e:
        _not_found(e)


# ── Create ────────────────────────────────────────────────────────────────

@router.post("", response_model=TopicOut, status_code=status.HTTP_201_CREATED)
async def create_topic_endpoint(
    web_name: str,
    data: TopicCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return await create_topic(db, web_name, data, author_id=current_user.id)
    except WebNotFound as e:
        _not_found(e)
    except TopicNameConflict as e:
        raise HTTPException(status_code=409, detail=str(e))


# ── Read (current or versioned) ───────────────────────────────────────────

@router.get("/{topic_name}", response_model=TopicOut)
async def get_topic_endpoint(
    web_name: str,
    topic_name: str,
    version: Optional[int] = Query(default=None, description="Specific version number"),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_topic(db, web_name, topic_name, version=version)
    except TopicNotFound as e:
        _not_found(e)


@router.get("/{topic_name}/raw", response_model=dict)
async def get_raw_endpoint(
    web_name: str,
    topic_name: str,
    version: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return raw TML/Markdown source without rendering."""
    try:
        t = await get_topic(db, web_name, topic_name, version=version)
        return {"web": web_name, "topic": topic_name, "version": t.current_version, "content": t.content}
    except TopicNotFound as e:
        _not_found(e)


# ── Save (new version) ────────────────────────────────────────────────────

@router.put("/{topic_name}", response_model=TopicOut)
async def save_topic_endpoint(
    web_name: str,
    topic_name: str,
    data: TopicSave,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return await save_topic(db, web_name, topic_name, data, author_id=current_user.id)
    except TopicNotFound as e:
        _not_found(e)


# ── Delete ────────────────────────────────────────────────────────────────

@router.delete("/{topic_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic_endpoint(
    web_name: str,
    topic_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        await delete_topic(db, web_name, topic_name)
    except TopicNotFound as e:
        _not_found(e)


# ── History ───────────────────────────────────────────────────────────────

@router.get("/{topic_name}/history", response_model=list[VersionOut])
async def get_history_endpoint(
    web_name: str,
    topic_name: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_history(db, web_name, topic_name)
    except TopicNotFound as e:
        _not_found(e)


@router.get("/{topic_name}/history/{ver}", response_model=VersionOut)
async def get_version_endpoint(
    web_name: str,
    topic_name: str,
    ver: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_version(db, web_name, topic_name, ver)
    except TopicNotFound as e:
        _not_found(e)


# ── Diff ──────────────────────────────────────────────────────────────────

@router.get("/{topic_name}/diff/{from_ver}/{to_ver}", response_model=DiffOut)
async def diff_endpoint(
    web_name: str,
    topic_name: str,
    from_ver: int,
    to_ver: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await diff_versions(db, web_name, topic_name, from_ver, to_ver)
    except TopicNotFound as e:
        _not_found(e)



