#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Topic service
=============
All topic operations: create, read (current + specific version), save new version,
delete, list, history, and unified diff between versions.
"""

from __future__ import annotations

import difflib
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.topic import Topic, TopicMeta, TopicVersion
from app.models.user import User
from app.models.web import Web
from app.schemas import (
    DiffOut, TopicCreate, TopicListItem, TopicOut,
    TopicSave, VersionOut,
)
from app.services.web_service import get_web_by_name, WebNotFound


class TopicNotFound(Exception):
    pass


class TopicNameConflict(Exception):
    pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _get_topic(db: AsyncSession, web_name: str, topic_name: str) -> Topic:
    """Load topic (without version content) or raise TopicNotFound."""
    result = await db.execute(
        select(Topic)
        .join(Web, Web.id == Topic.web_id)
        .where(Web.name == web_name, Topic.name == topic_name)
    )
    topic = result.scalar_one_or_none()
    if topic is None:
        raise TopicNotFound(f"{web_name}.{topic_name} not found")
    return topic


async def _get_latest_version(db: AsyncSession, topic_id: uuid.UUID) -> Optional[TopicVersion]:
    result = await db.execute(
        select(TopicVersion)
        .where(TopicVersion.topic_id == topic_id)
        .order_by(TopicVersion.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_meta(db: AsyncSession, topic_id: uuid.UUID) -> dict[str, str]:
    result = await db.execute(
        select(TopicMeta).where(TopicMeta.topic_id == topic_id)
    )
    return {row.key: row.value for row in result.scalars().all()}


async def _build_topic_out(
    db: AsyncSession, web: Web, topic: Topic, version: TopicVersion
) -> TopicOut:
    meta = await _get_meta(db, topic.id)
    author_name: Optional[str] = None
    if version.author_id:
        res = await db.execute(select(User).where(User.id == version.author_id))
        u = res.scalar_one_or_none()
        if u:
            author_name = u.username
    return TopicOut(
        id=topic.id,
        web_id=topic.web_id,
        web_name=web.name,
        name=topic.name,
        created_at=topic.created_at,
        current_version=version.version,
        modified_at=version.created_at,
        modified_by=author_name,
        content=version.content,
        meta=meta,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Public API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def list_topics(
    db: AsyncSession, web_name: str, search: Optional[str] = None
) -> list[TopicListItem]:
    """Return all topics in a web with their latest version summary."""
    web = await get_web_by_name(db, web_name)

    # Subquery: latest version number per topic
    latest_ver_sq = (
        select(
            TopicVersion.topic_id,
            func.max(TopicVersion.version).label("max_ver"),
        )
        .group_by(TopicVersion.topic_id)
        .subquery()
    )

    q = (
        select(Topic, TopicVersion, User.username)
        .join(latest_ver_sq, latest_ver_sq.c.topic_id == Topic.id)
        .join(
            TopicVersion,
            (TopicVersion.topic_id == Topic.id)
            & (TopicVersion.version == latest_ver_sq.c.max_ver),
        )
        .outerjoin(User, User.id == TopicVersion.author_id)
        .where(Topic.web_id == web.id)
        .order_by(Topic.name)
    )

    if search:
        q = q.where(Topic.name.ilike(f"%{search}%"))

    result = await db.execute(q)
    items = []
    for topic, version, username in result.all():
        items.append(TopicListItem(
            id=topic.id,
            name=topic.name,
            current_version=version.version,
            modified_at=version.created_at,
            modified_by=username,
        ))
    return items


async def get_topic(
    db: AsyncSession, web_name: str, topic_name: str, version: Optional[int] = None
) -> TopicOut:
    """Fetch a topic's current (or specific versioned) content."""
    web = await get_web_by_name(db, web_name)
    topic = await _get_topic(db, web_name, topic_name)

    if version is not None:
        result = await db.execute(
            select(TopicVersion).where(
                TopicVersion.topic_id == topic.id,
                TopicVersion.version == version,
            )
        )
        ver = result.scalar_one_or_none()
        if ver is None:
            raise TopicNotFound(f"{web_name}.{topic_name} v{version} not found")
    else:
        ver = await _get_latest_version(db, topic.id)
        if ver is None:
            raise TopicNotFound(f"{web_name}.{topic_name} has no versions")

    return await _build_topic_out(db, web, topic, ver)


async def create_topic(
    db: AsyncSession,
    web_name: str,
    data: TopicCreate,
    author_id: Optional[uuid.UUID] = None,
) -> TopicOut:
    """Create a new topic with version 1."""
    web = await get_web_by_name(db, web_name)

    # Uniqueness check
    existing = await db.execute(
        select(Topic).join(Web, Web.id == Topic.web_id).where(
            Web.name == web_name, Topic.name == data.name
        )
    )
    if existing.scalar_one_or_none():
        raise TopicNameConflict(f"{web_name}.{data.name} already exists")

    topic = Topic(web_id=web.id, name=data.name, created_by_id=author_id)
    db.add(topic)
    await db.flush()

    version = TopicVersion(
        topic_id=topic.id,
        version=1,
        content=data.content,
        comment=data.comment,
        author_id=author_id,
    )
    db.add(version)

    # Meta fields
    for key, value in data.meta.items():
        db.add(TopicMeta(topic_id=topic.id, key=key, value=value))

    await db.flush()
    await db.refresh(topic)
    await db.refresh(version)
    return await _build_topic_out(db, web, topic, version)


async def save_topic(
    db: AsyncSession,
    web_name: str,
    topic_name: str,
    data: TopicSave,
    author_id: Optional[uuid.UUID] = None,
) -> TopicOut:
    """Save new version of an existing topic."""
    web = await get_web_by_name(db, web_name)
    topic = await _get_topic(db, web_name, topic_name)
    latest = await _get_latest_version(db, topic.id)
    next_ver = (latest.version + 1) if latest else 1

    version = TopicVersion(
        topic_id=topic.id,
        version=next_ver,
        content=data.content,
        comment=data.comment,
        author_id=author_id,
    )
    db.add(version)

    # Update meta if provided
    if data.meta is not None:
        # Delete existing and replace
        existing_meta = await db.execute(
            select(TopicMeta).where(TopicMeta.topic_id == topic.id)
        )
        for row in existing_meta.scalars().all():
            await db.delete(row)
        for key, value in data.meta.items():
            db.add(TopicMeta(topic_id=topic.id, key=key, value=value))

    await db.flush()
    await db.refresh(version)
    return await _build_topic_out(db, web, topic, version)


async def delete_topic(db: AsyncSession, web_name: str, topic_name: str) -> None:
    """Delete a topic and all its versions (cascade)."""
    topic = await _get_topic(db, web_name, topic_name)
    await db.delete(topic)
    await db.flush()


async def get_history(
    db: AsyncSession, web_name: str, topic_name: str
) -> list[VersionOut]:
    """Return version history (newest first) without content."""
    topic = await _get_topic(db, web_name, topic_name)

    result = await db.execute(
        select(TopicVersion, User.username)
        .outerjoin(User, User.id == TopicVersion.author_id)
        .where(TopicVersion.topic_id == topic.id)
        .order_by(TopicVersion.version.desc())
    )
    out = []
    for ver, username in result.all():
        out.append(VersionOut(
            id=ver.id,
            topic_id=ver.topic_id,
            version=ver.version,
            comment=ver.comment,
            author=username,
            created_at=ver.created_at,
        ))
    return out


async def get_version(
    db: AsyncSession, web_name: str, topic_name: str, version: int
) -> VersionOut:
    """Return a specific version including its content."""
    topic = await _get_topic(db, web_name, topic_name)

    result = await db.execute(
        select(TopicVersion, User.username)
        .outerjoin(User, User.id == TopicVersion.author_id)
        .where(TopicVersion.topic_id == topic.id, TopicVersion.version == version)
    )
    row = result.first()
    if row is None:
        raise TopicNotFound(f"{web_name}.{topic_name} v{version} not found")
    ver, username = row
    return VersionOut(
        id=ver.id,
        topic_id=ver.topic_id,
        version=ver.version,
        comment=ver.comment,
        author=username,
        created_at=ver.created_at,
        content=ver.content,
    )


async def diff_versions(
    db: AsyncSession, web_name: str, topic_name: str, from_ver: int, to_ver: int
) -> DiffOut:
    """Produce a unified diff between two versions."""
    topic = await _get_topic(db, web_name, topic_name)

    async def _fetch(v: int) -> str:
        res = await db.execute(
            select(TopicVersion.content).where(
                TopicVersion.topic_id == topic.id, TopicVersion.version == v
            )
        )
        content = res.scalar_one_or_none()
        if content is None:
            raise TopicNotFound(f"{web_name}.{topic_name} v{v} not found")
        return content

    from_content = await _fetch(from_ver)
    to_content = await _fetch(to_ver)

    diff_lines = list(difflib.unified_diff(
        from_content.splitlines(keepends=True),
        to_content.splitlines(keepends=True),
        fromfile=f"{web_name}.{topic_name} v{from_ver}",
        tofile=f"{web_name}.{topic_name} v{to_ver}",
        lineterm="",
    ))

    return DiffOut(
        web=web_name,
        topic=topic_name,
        from_version=from_ver,
        to_version=to_ver,
        unified_diff="".join(diff_lines),
    )



