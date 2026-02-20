#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Web service — CRUD for the Web namespace model.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.web import Web
from app.models.topic import Topic
from app.schemas import WebCreate, WebUpdate, WebOut


class WebNotFound(Exception):
    pass


class WebNameConflict(Exception):
    pass


async def list_webs(db: AsyncSession) -> list[WebOut]:
    result = await db.execute(
        select(
            Web,
            func.count(Topic.id).label("topic_count"),
        )
        .outerjoin(Topic, Topic.web_id == Web.id)
        .group_by(Web.id)
        .order_by(Web.name)
    )
    rows = result.all()
    out = []
    for web, count in rows:
        out.append(WebOut(
            id=web.id,
            name=web.name,
            description=web.description,
            parent_id=web.parent_id,
            created_at=web.created_at,
            topic_count=count,
        ))
    return out


async def get_web_by_name(db: AsyncSession, name: str) -> Web:
    result = await db.execute(select(Web).where(Web.name == name))
    web = result.scalar_one_or_none()
    if web is None:
        raise WebNotFound(f"Web '{name}' not found")
    return web


async def get_web_by_id(db: AsyncSession, web_id: uuid.UUID) -> Web:
    result = await db.execute(select(Web).where(Web.id == web_id))
    web = result.scalar_one_or_none()
    if web is None:
        raise WebNotFound(f"Web id={web_id} not found")
    return web


async def create_web(db: AsyncSession, data: WebCreate) -> Web:
    # Check uniqueness
    existing = await db.execute(select(Web).where(Web.name == data.name))
    if existing.scalar_one_or_none():
        raise WebNameConflict(f"Web '{data.name}' already exists")

    web = Web(
        name=data.name,
        description=data.description,
        parent_id=data.parent_id,
    )
    db.add(web)
    await db.flush()
    await db.refresh(web)
    return web


async def update_web(db: AsyncSession, name: str, data: WebUpdate) -> Web:
    web = await get_web_by_name(db, name)
    if data.description is not None:
        web.description = data.description
    await db.flush()
    await db.refresh(web)
    return web


async def delete_web(db: AsyncSession, name: str) -> None:
    web = await get_web_by_name(db, name)
    await db.delete(web)
    await db.flush()




