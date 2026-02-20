#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""Search page."""
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.core.database import get_db
from app.models import Topic, TopicVersion, User, Web
from webui.context import PageContext
from webui.session import get_current_user
from webui.templating import templates

router = APIRouter(tags=["webui-search"])


# -----------------------------------------------------------------------------

@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = "",
    web: str = "",
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    results = []
    if q:
        pattern = f"%{q}%"
        latest_sq = (
            select(TopicVersion.topic_id, func.max(TopicVersion.version).label("max_ver"))
            .group_by(TopicVersion.topic_id)
            .subquery()
        )
        stmt = (
            select(Web.name.label("web_name"), Topic.name.label("topic_name"),
                   TopicVersion.version, TopicVersion.content, TopicVersion.created_at, User.username)
            .join(Topic, Topic.web_id == Web.id)
            .join(latest_sq, latest_sq.c.topic_id == Topic.id)
            .join(TopicVersion, (TopicVersion.topic_id == Topic.id) & (TopicVersion.version == latest_sq.c.max_ver))
            .outerjoin(User, User.id == TopicVersion.author_id)
            .where(Topic.name.ilike(pattern) | TopicVersion.content.ilike(pattern))
        )
        if web:
            stmt = stmt.where(Web.name == web)
        stmt = stmt.order_by(Web.name, Topic.name).limit(50)
        rows = (await db.execute(stmt)).all()
        results = [
            {
                "web": r.web_name,
                "topic": r.topic_name,
                "version": r.version,
                "author": r.username,
                "modified_at": r.created_at,
                "excerpt": _excerpt(r.content, q),
                "url": f"/webs/{r.web_name}/topics/{r.topic_name}",
            }
            for r in rows
        ]

    ctx = PageContext(title="Search", user=user)
    return templates.TemplateResponse("search.html", {
        **ctx.to_dict(request),
        "q": q,
        "web_filter": web,
        "results": results,
    })


def _excerpt(content: str, query: str, radius: int = 120) -> str:
    if not content:
        return ""
    idx = content.lower().find(query.lower())
    if idx == -1:
        return content[:radius * 2] + ("…" if len(content) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(content), idx + len(query) + radius)
    snippet = content[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(content):
        snippet += "…"
    return snippet
