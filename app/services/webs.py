#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Web service — create, read, list, and delete wiki webs (namespaces).
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


# -----------------------------------------------------------------------------

from app.models import Web, Topic
from app.schemas import WebCreate, WebUpdate


# -----------------------------------------------------------------------------

async def create_web(db: AsyncSession, data: WebCreate) -> Web:
    # Uniqueness check
    existing = await db.execute(select(Web).where(Web.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Web '{data.name}' already exists",
        )

    parent_id = None
    if data.parent_name:
        parent = await get_web_by_name(db, data.parent_name)
        parent_id = parent.id

    web = Web(name=data.name, description=data.description, parent_id=parent_id)
    db.add(web)
    await db.flush()
    return web


# -----------------------------------------------------------------------------

async def get_web_by_name(db: AsyncSession, name: str) -> Web:
    result = await db.execute(select(Web).where(Web.name == name))
    web = result.scalar_one_or_none()
    if not web:
        raise HTTPException(status_code=404, detail=f"Web '{name}' not found")
    return web


# -----------------------------------------------------------------------------

async def get_web_by_id(db: AsyncSession, web_id: str) -> Web:
    web = await db.get(Web, web_id)
    if not web:
        raise HTTPException(status_code=404, detail="Web not found")
    return web


# -----------------------------------------------------------------------------

async def list_webs(db: AsyncSession, skip: int = 0, limit: int = 100) -> list[Web]:
    result = await db.execute(select(Web).order_by(Web.name).offset(skip).limit(limit))
    return list(result.scalars().all())


# -----------------------------------------------------------------------------

async def update_web(db: AsyncSession, name: str, data: WebUpdate) -> Web:
    web = await get_web_by_name(db, name)
    if data.description is not None:
        web.description = data.description
    await db.flush()
    return web


# -----------------------------------------------------------------------------

async def delete_web(db: AsyncSession, name: str) -> None:
    web = await get_web_by_name(db, name)
    # Check for topics
    count_result = await db.execute(
        select(func.count()).select_from(Topic).where(Topic.web_id == web.id)
    )
    if count_result.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a web that contains topics",
        )
    await db.delete(web)


# -----------------------------------------------------------------------------

async def get_topic_count(db: AsyncSession, web_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(Topic).where(Topic.web_id == web_id)
    )
    return result.scalar_one()


# -----------------------------------------------------------------------------

