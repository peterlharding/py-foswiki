#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Search router
=============
GET /api/v1/search?q=...&web=...&scope=...&limit=...

Simple PostgreSQL ILIKE / SQLite LIKE search over topic names and content.
Phase 5 can swap in Meilisearch/Solr without changing the router contract.
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Topic, TopicVersion, User, Web

# -----------------------------------------------------------------------------

router = APIRouter(prefix="/search", tags=["Search"])


# -----------------------------------------------------------------------------

class SearchResult(BaseModel):
    web: str
    topic: str
    version: int
    author: Optional[str]
    modified_at: str
    excerpt: str
    url: str


# -----------------------------------------------------------------------------

@router.get("", response_model=list[SearchResult])
async def search(
    q: str = Query(min_length=1, description="Search query"),
    web: Optional[str] = Query(default=None, description="Restrict to a specific web"),
    scope: str = Query(default="all", description="'topic', 'content', or 'all'"),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    Search topic names and/or content using ILIKE (case-insensitive).
    Returns the latest version of each matching topic.

    For production scale, replace with PostgreSQL FTS vectors or Meilisearch.
    """
    pattern = f"%{q}%"

    # Subquery: latest version number per topic
    latest_sq = (
        select(
            TopicVersion.topic_id,
            func.max(TopicVersion.version).label("max_ver"),
        )
        .group_by(TopicVersion.topic_id)
        .subquery()
    )

    stmt = (
        select(
            Web.name.label("web_name"),
            Topic.name.label("topic_name"),
            TopicVersion.version,
            TopicVersion.content,
            TopicVersion.created_at,
            User.username,
        )
        .join(Topic, Topic.web_id == Web.id)
        .join(latest_sq, latest_sq.c.topic_id == Topic.id)
        .join(
            TopicVersion,
            (TopicVersion.topic_id == Topic.id)
            & (TopicVersion.version == latest_sq.c.max_ver),
        )
        .outerjoin(User, User.id == TopicVersion.author_id)
    )

    if web:
        stmt = stmt.where(Web.name == web)

    if scope == "topic":
        stmt = stmt.where(Topic.name.ilike(pattern))
    elif scope == "content":
        stmt = stmt.where(TopicVersion.content.ilike(pattern))
    else:  # all
        stmt = stmt.where(
            Topic.name.ilike(pattern) | TopicVersion.content.ilike(pattern)
        )

    stmt = stmt.order_by(Web.name, Topic.name).limit(limit)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        SearchResult(
            web=web_name,
            topic=topic_name,
            version=version,
            author=username,
            modified_at=str(modified_at),
            excerpt=_excerpt(content, q),
            url=f"/view/{web_name}/{topic_name}",
        )
        for web_name, topic_name, version, content, modified_at, username in rows
    ]


# -----------------------------------------------------------------------------

def _excerpt(content: str, query: str, radius: int = 100) -> str:
    """Return a short snippet of *content* centred around the first match of *query*."""
    if not content:
        return ""
    lower = content.lower()
    idx = lower.find(query.lower())
    if idx == -1:
        return content[: radius * 2] + ("…" if len(content) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(content), idx + len(query) + radius)
    snippet = content[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(content):
        snippet = snippet + "…"
    return snippet


# -----------------------------------------------------------------------------
