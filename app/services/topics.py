#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Topic service
=============
Versioned create / read / update / rename / delete for wiki topics.

Every save appends a new TopicVersion row — nothing is overwritten.
Diffs use Python's difflib SequenceMatcher.
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import difflib
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


# -----------------------------------------------------------------------------

from app.models import Topic, TopicMeta, TopicVersion, User, Web
from app.schemas import TopicCreate, TopicRename, TopicUpdate

from .webs import get_web_by_name


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _get_topic(db: AsyncSession, web_id: str, name: str) -> Topic:
    result = await db.execute(
        select(Topic)
        .where(Topic.web_id == web_id, Topic.name == name)
        .options(
            selectinload(Topic.versions).selectinload(TopicVersion.author),
            selectinload(Topic.meta),
        )
    )
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail=f"Topic '{name}' not found")
    return topic


# -----------------------------------------------------------------------------

async def _latest_version(db: AsyncSession, topic_id: str) -> Optional[TopicVersion]:
    result = await db.execute(
        select(TopicVersion)
        .where(TopicVersion.topic_id == topic_id)
        .order_by(TopicVersion.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# -----------------------------------------------------------------------------

async def _next_version_number(db: AsyncSession, topic_id: str) -> int:
    result = await db.execute(
        select(func.max(TopicVersion.version)).where(TopicVersion.topic_id == topic_id)
    )
    current = result.scalar_one_or_none()
    return (current or 0) + 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def create_topic(
    db: AsyncSession,
    web_name: str,
    data: TopicCreate,
    author_id: Optional[str] = None,
) -> tuple[Topic, TopicVersion]:
    web = await get_web_by_name(db, web_name)

    # Duplicate check
    exists = await db.execute(
        select(Topic).where(Topic.web_id == web.id, Topic.name == data.name)
    )
    if exists.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Topic '{data.name}' already exists in web '{web_name}'",
        )

    topic = Topic(web_id=web.id, name=data.name, created_by=author_id)
    db.add(topic)
    await db.flush()   # get topic.id

    # First version
    version = TopicVersion(
        topic_id=topic.id,
        version=1,
        content=data.content,
        author_id=author_id,
        comment=data.comment or "Initial version",
    )
    db.add(version)

    # Metadata
    for key, value in (data.meta or {}).items():
        db.add(TopicMeta(topic_id=topic.id, key=key, value=value))

    await db.flush()

    # Reload with all relations eagerly loaded
    topic, version = await _reload_topic_version(db, topic.id, version.version)
    return topic, version


# -----------------------------------------------------------------------------

async def get_topic(
    db: AsyncSession,
    web_name: str,
    topic_name: str,
    version: Optional[int] = None,
) -> tuple[Topic, TopicVersion]:
    """Return (topic, version_row).  Defaults to latest version."""
    web = await get_web_by_name(db, web_name)
    topic = await _get_topic(db, web.id, topic_name)

    if version is not None:
        ver = next((v for v in topic.versions if v.version == version), None)
        if not ver:
            raise HTTPException(status_code=404, detail=f"Version {version} not found")
    else:
        ver = max(topic.versions, key=lambda v: v.version) if topic.versions else None
        if not ver:
            raise HTTPException(status_code=404, detail="Topic has no content")

    return topic, ver


# -----------------------------------------------------------------------------

async def update_topic(
    db: AsyncSession,
    web_name: str,
    topic_name: str,
    data: TopicUpdate,
    author_id: Optional[str] = None,
) -> tuple[Topic, TopicVersion]:
    web = await get_web_by_name(db, web_name)
    topic = await _get_topic(db, web.id, topic_name)

    next_ver = await _next_version_number(db, topic.id)
    # Invalidate cached render on previous version
    prev = await _latest_version(db, topic.id)
    if prev:
        prev.rendered = None

    new_version = TopicVersion(
        topic_id=topic.id,
        version=next_ver,
        content=data.content,
        author_id=author_id,
        comment=data.comment or f"Version {next_ver}",
    )
    db.add(new_version)

    # Merge metadata if provided
    if data.meta is not None:
        # Delete old meta then re-insert (simple replace strategy)
        for m in topic.meta:
            await db.delete(m)
        await db.flush()
        for key, value in data.meta.items():
            db.add(TopicMeta(topic_id=topic.id, key=key, value=value))

    await db.flush()

    # Reload with all relations
    topic, new_version = await _reload_topic_version(db, topic.id, new_version.version)
    return topic, new_version


# -----------------------------------------------------------------------------

async def rename_topic(
    db: AsyncSession,
    web_name: str,
    topic_name: str,
    data: TopicRename,
    author_id: Optional[str] = None,
) -> Topic:
    web = await get_web_by_name(db, web_name)
    topic = await _get_topic(db, web.id, topic_name)

    conflict = await db.execute(
        select(Topic).where(Topic.web_id == web.id, Topic.name == data.new_name)
    )
    if conflict.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Topic '{data.new_name}' already exists",
        )

    topic.name = data.new_name
    await db.flush()
    return topic


# -----------------------------------------------------------------------------

async def delete_topic(
    db: AsyncSession,
    web_name: str,
    topic_name: str,
) -> None:
    web = await get_web_by_name(db, web_name)
    topic = await _get_topic(db, web.id, topic_name)
    await db.delete(topic)


# -----------------------------------------------------------------------------

async def list_topics(
    db: AsyncSession,
    web_name: str,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
) -> list[dict]:
    """Return lightweight summaries (no content body)."""
    web = await get_web_by_name(db, web_name)

    # Subquery: latest version per topic
    max_ver_sub = (
        select(
            TopicVersion.topic_id,
            func.max(TopicVersion.version).label("max_ver"),
        )
        .group_by(TopicVersion.topic_id)
        .subquery()
    )

    q = (
        select(Topic, TopicVersion, User)
        .join(max_ver_sub, Topic.id == max_ver_sub.c.topic_id)
        .join(
            TopicVersion,
            (TopicVersion.topic_id == Topic.id) &
            (TopicVersion.version == max_ver_sub.c.max_ver),
        )
        .outerjoin(User, User.id == TopicVersion.author_id)
        .where(Topic.web_id == web.id)
        .order_by(Topic.name)
        .offset(skip)
        .limit(limit)
    )

    if search:
        q = q.where(Topic.name.ilike(f"%{search}%"))

    result = await db.execute(q)
    rows = result.all()

    return [
        {
            "id":              t.id,
            "web":             web_name,
            "name":            t.name,
            "version":         v.version,
            "author_username": u.username if u else None,
            "updated_at":      v.created_at,
        }
        for t, v, u in rows
    ]


# -----------------------------------------------------------------------------

async def get_topic_history(
    db: AsyncSession,
    web_name: str,
    topic_name: str,
) -> list[TopicVersion]:
    web = await get_web_by_name(db, web_name)
    topic = await _get_topic(db, web.id, topic_name)
    return sorted(topic.versions, key=lambda v: v.version, reverse=True)


# -----------------------------------------------------------------------------

async def get_diff(
    db: AsyncSession,
    web_name: str,
    topic_name: str,
    from_ver: int,
    to_ver: int,
) -> list[dict]:
    """
    Return a structured diff between two versions.

    Each item: {"type": "equal"|"insert"|"delete", "lines": ["..."]}
    """
    web = await get_web_by_name(db, web_name)
    topic = await _get_topic(db, web.id, topic_name)

    ver_map = {v.version: v for v in topic.versions}
    a_ver = ver_map.get(from_ver)
    b_ver = ver_map.get(to_ver)

    if not a_ver:
        raise HTTPException(status_code=404, detail=f"Version {from_ver} not found")
    if not b_ver:
        raise HTTPException(status_code=404, detail=f"Version {to_ver} not found")

    a_lines = a_ver.content.splitlines(keepends=True)
    b_lines = b_ver.content.splitlines(keepends=True)

    diff_groups = []
    matcher = difflib.SequenceMatcher(None, a_lines, b_lines)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            diff_groups.append({"type": "equal",  "lines": a_lines[i1:i2]})
        elif tag == "replace":
            diff_groups.append({"type": "delete",  "lines": a_lines[i1:i2]})
            diff_groups.append({"type": "insert",  "lines": b_lines[j1:j2]})
        elif tag == "delete":
            diff_groups.append({"type": "delete",  "lines": a_lines[i1:i2]})
        elif tag == "insert":
            diff_groups.append({"type": "insert",  "lines": b_lines[j1:j2]})

    return diff_groups


# -----------------------------------------------------------------------------

async def _reload_topic_version(
    db: AsyncSession, topic_id: str, version_num: int
) -> tuple["Topic", "TopicVersion"]:
    """Reload topic and specific version with all relationships eagerly loaded."""
    # Expire so SQLAlchemy re-fetches from DB rather than using identity map
    db.expire_all()
    result = await db.execute(
        select(Topic)
        .where(Topic.id == topic_id)
        .options(
            selectinload(Topic.versions).selectinload(TopicVersion.author),
            selectinload(Topic.meta),
            selectinload(Topic.attachments),
        )
    )
    topic = result.scalar_one()
    matches = [v for v in topic.versions if v.version == version_num]
    if not matches:
        raise RuntimeError(f"Version {version_num} not found after flush")
    return topic, matches[0]


# -----------------------------------------------------------------------------

