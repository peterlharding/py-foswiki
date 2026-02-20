#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Webs router
===========
GET    /api/v1/webs              — list all webs
POST   /api/v1/webs              — create a new web  [auth required]
GET    /api/v1/webs/{web}        — get web details
PATCH  /api/v1/webs/{web}        — update description  [auth required]
DELETE /api/v1/webs/{web}        — delete empty web    [admin required]
GET    /api/v1/webs/{web}/acl    — get ACL
PUT    /api/v1/webs/{web}/acl    — set ACL             [admin required]
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id, get_optional_user_id
from app.schemas import ACLResponse, ACLUpdate, OKResponse, WebCreate, WebResponse, WebUpdate
from app.services import acl as acl_svc
from app.services import webs as web_svc
from app.services.users import get_user_by_id

# -----------------------------------------------------------------------------

router = APIRouter(prefix="/webs", tags=["webs"])


# -----------------------------------------------------------------------------

@router.get("", response_model=list[WebResponse])
async def list_webs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    webs = await web_svc.list_webs(db, skip=skip, limit=limit)
    results = []
    for w in webs:
        count = await web_svc.get_topic_count(db, w.id)
        results.append({**_web_dict(w), "topic_count": count})
    return results


# -----------------------------------------------------------------------------

@router.post("", response_model=WebResponse, status_code=201)
async def create_web(
    data: WebCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    web = await web_svc.create_web(db, data)
    return _web_dict(web)


# -----------------------------------------------------------------------------

@router.get("/{web_name}", response_model=WebResponse)
async def get_web(web_name: str, db: AsyncSession = Depends(get_db)):
    web = await web_svc.get_web_by_name(db, web_name)
    count = await web_svc.get_topic_count(db, web.id)
    return {**_web_dict(web), "topic_count": count}


# -----------------------------------------------------------------------------

@router.patch("/{web_name}", response_model=WebResponse)
async def update_web(
    web_name: str,
    data: WebUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    web = await web_svc.update_web(db, web_name, data)
    return _web_dict(web)


# -----------------------------------------------------------------------------

@router.delete("/{web_name}", response_model=OKResponse)
async def delete_web(
    web_name: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    await web_svc.delete_web(db, web_name)
    return OKResponse(message=f"Web '{web_name}' deleted")


# -----------------------------------------------------------------------------

@router.get("/{web_name}/acl", response_model=ACLResponse)
async def get_acl(
    web_name: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    web = await web_svc.get_web_by_name(db, web_name)
    entries = await acl_svc.get_acl(db, "web", web.id)
    return ACLResponse(
        resource_type="web",
        resource_id=web.id,
        entries=[{"principal": e.principal, "permission": e.permission, "allow": e.allow} for e in entries],
    )


# -----------------------------------------------------------------------------

@router.put("/{web_name}/acl", response_model=ACLResponse)
async def set_acl(
    web_name: str,
    data: ACLUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    web = await web_svc.get_web_by_name(db, web_name)
    entries = await acl_svc.set_acl(db, "web", web.id, data)
    return ACLResponse(
        resource_type="web",
        resource_id=web.id,
        entries=[{"principal": e.principal, "permission": e.permission, "allow": e.allow} for e in entries],
    )


# -----------------------------------------------------------------------------

def _web_dict(w) -> dict:
    return {
        "id":          w.id,
        "name":        w.name,
        "description": w.description,
        "parent_id":   w.parent_id,
        "created_at":  w.created_at,
    }


# -----------------------------------------------------------------------------
