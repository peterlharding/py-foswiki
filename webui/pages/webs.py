#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""Webs list and web detail (topic list) pages."""
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import webs as web_svc
from app.services import topics as topic_svc
from app.schemas import WebCreate
from webui.context import PageContext
from webui.session import get_current_user
from webui.templating import templates

router = APIRouter(tags=["webui-webs"])


# -----------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    webs = await web_svc.list_webs(db)
    ctx = PageContext(title="PyFoswiki", user=user)
    return templates.TemplateResponse("webs/list.html", {
        **ctx.to_dict(request),
        "webs": webs,
    })


@router.get("/webs", response_class=HTMLResponse)
async def webs_list(request: Request, db: AsyncSession = Depends(get_db)):
    return RedirectResponse(url="/", status_code=302)


# -----------------------------------------------------------------------------

@router.get("/webs/new", response_class=HTMLResponse)
async def new_web_page(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    ctx = PageContext(title="New Web", user=user)
    return templates.TemplateResponse("webs/new.html", {
        **ctx.to_dict(request),
        "error": "",
    })


@router.post("/webs/new")
async def new_web_submit(
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    try:
        await web_svc.create_web(db, WebCreate(name=name, description=description))
        return RedirectResponse(url=f"/webs/{name}", status_code=302)
    except Exception as e:
        ctx = PageContext(title="New Web", user=user)
        return templates.TemplateResponse("webs/new.html", {
            **ctx.to_dict(request),
            "error": str(e),
        }, status_code=400)


# -----------------------------------------------------------------------------

@router.get("/webs/{web_name}", response_class=HTMLResponse)
async def web_detail(
    web_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    web = await web_svc.get_web_by_name(db, web_name)
    topics = await topic_svc.list_topics(db, web_name)
    ctx = PageContext(title=f"{web_name} — Topics", user=user, web=web_name)
    return templates.TemplateResponse("webs/detail.html", {
        **ctx.to_dict(request),
        "web": web,
        "topics": topics,
    })
