#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Search router
=============
GET /api/v1/search?q=...&web=...&scope=...&limit=...

Simple PostgreSQL full-text / ILIKE search.
Phase 5 can swap in Meilisearch/Solr without changing the router.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.topic import Topic, TopicVersion
from app.models.user import User
from app.models.web import Web

router = APIRouter(prefix="/search", tags=["Search"])


class SearchResult(BaseModel):
    web: str
    topic: str
    version: int
    author: Optional[str]
    modified_at: str
    excerpt: str
    url: str


@router.get("", response_model=list[SearchResult])
async def search(
    q: str = Query(min_length=1, description="Search query"),
    web: Optional[str] = Query(default=None, description="Restrict to a specific web"),
    scope: str = Query(default="all", description="'topic', 'content', or 'all'"),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    Fast search using PostgreSQL ILIKE.
    For production scale, replace with Meilisearch or Postgres FTS vectors.
    """
    pattern = f"%{q}%"

    # Subquery: latest version per topic
    latest_sq = (
        select(
            TopicVersion.topic_id,
            TopicVersion.version,
            TopicVersion.content,
            TopicVersion.created_at,
            TopicVersion.author_id,
        )
        .distinct(TopicVersion.topic_id)
        .order_by(TopicVersion.topic_id, TopicVersion.version.desc())
        .subquery("latest")
    )

    stmt = (
        select(
            Web.name.label("web_name"),
            Topic.name.label("topic_name"),
            latest_sq.c.version,
            latest_sq.c.content,
            latest_sq.c.created_at,
            User.username,
        )
        .join(Topic, Topic.web_id == Web.id)
        .join(latest_sq, latest_sq.c.topic_id == Topic.id)
        .outerjoin(User, User.id == latest_sq.c.author_id)
    )

    # Apply web filter
    if web:
        stmt = stmt.where(Web.name == web)

    # Apply scope filter
    if scope == "topic":
        stmt = stmt.where(Topic.name.ilike(pattern))
    elif scope == "content":
        stmt = stmt.where(latest_sq.c.content.ilike(pattern))
    else:  # all
        stmt = stmt.where(
            Topic.name.ilike(pattern) | latest_sq.c.content.ilike(pattern)
        )

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    rows = result.all()

    out = []
    for web_name, topic_name, version, content, modified_at, username in rows:
        excerpt = _excerpt(content, q)
        out.append(SearchResult(
            web=web_name,
            topic=topic_name,
            version=version,
            author=username,
            modified_at=str(modified_at),
            excerpt=excerpt,
            url=f"/view/{web_name}/{topic_name}",
        ))
    return out


def _excerpt(content: str, query: str, radius: int = 100) -> str:
    """Return a short snippet around the first query match."""
    if not content:
        return ""
    lower = content.lower()
    idx = lower.find(query.lower())
    if idx == -1:
        return content[:radius * 2] + ("…" if len(content) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(content), idx + len(query) + radius)
    snippet = content[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(content):
        snippet = snippet + "…"
    return snippet



