#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Webs router
===========
GET    /api/v1/webs                — list all webs
POST   /api/v1/webs                — create web  (auth required)
GET    /api/v1/webs/{web}          — get web info
PUT    /api/v1/webs/{web}          — update web  (auth required)
DELETE /api/v1/webs/{web}          — delete web  (admin required)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.models.user import User
from app.schemas import WebCreate, WebOut, WebUpdate
from app.services.web_service import (
    WebNameConflict,
    WebNotFound,
    create_web,
    delete_web,
    get_web_by_name,
    list_webs,
    update_web,
)

router = APIRouter(prefix="/webs", tags=["Webs"])


@router.get("", response_model=list[WebOut])
async def list_webs_endpoint(db: AsyncSession = Depends(get_db)):
    return await list_webs(db)


@router.post("", response_model=WebOut, status_code=status.HTTP_201_CREATED)
async def create_web_endpoint(
    data: WebCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        web = await create_web(db, data)
    except WebNameConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    return WebOut(
        id=web.id,
        name=web.name,
        description=web.description,
        parent_id=web.parent_id,
        created_at=web.created_at,
        topic_count=0,
    )


@router.get("/{web_name}", response_model=WebOut)
async def get_web_endpoint(web_name: str, db: AsyncSession = Depends(get_db)):
    try:
        webs = await list_webs(db)
        for w in webs:
            if w.name == web_name:
                return w
        raise WebNotFound(f"Web '{web_name}' not found")
    except WebNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{web_name}", response_model=WebOut)
async def update_web_endpoint(
    web_name: str,
    data: WebUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        web = await update_web(db, web_name, data)
    except WebNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return WebOut(
        id=web.id,
        name=web.name,
        description=web.description,
        parent_id=web.parent_id,
        created_at=web.created_at,
    )


@router.delete("/{web_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_web_endpoint(
    web_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required to delete webs")
    try:
        await delete_web(db, web_name)
    except WebNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))



