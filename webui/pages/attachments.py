#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""
Attachment web UI pages.

GET  /webs/{web}/topics/{topic}/attachments          — list + upload form
POST /webs/{web}/topics/{topic}/attachments          — upload file
POST /webs/{web}/topics/{topic}/attachments/{f}/delete — delete file
GET  /webs/{web}/topics/{topic}/attachments/{f}      — download (proxies API storage)
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.services import attachments as att_svc
from webui.context import PageContext
from webui.session import get_current_user
from webui.templating import templates

router = APIRouter(tags=["webui-attachments"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 ** 2:.1f} MB"


# ── List + upload form ────────────────────────────────────────────────────────

@router.get("/webs/{web_name}/topics/{topic_name}/attachments", response_class=HTMLResponse)
async def attachments_page(
    web_name: str,
    topic_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    try:
        attachments = await att_svc.list_attachments(db, web_name, topic_name)
    except Exception:
        attachments = []
    ctx = PageContext(
        title=f"Attachments — {web_name}.{topic_name}",
        user=user, web=web_name, topic=topic_name,
    )
    return templates.TemplateResponse("topics/attachments.html", {
        **ctx.to_dict(request),
        "web": web_name,
        "topic_name": topic_name,
        "attachments": attachments,
        "fmt_size": _fmt_size,
        "error": "",
        "success": "",
    })


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/webs/{web_name}/topics/{topic_name}/attachments")
async def upload_attachment(
    web_name: str,
    topic_name: str,
    request: Request,
    file: UploadFile = File(...),
    comment: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    try:
        await att_svc.upload_attachment(
            db, web_name, topic_name, file,
            comment=comment, author_id=user["id"],
        )
        return RedirectResponse(
            url=f"/webs/{web_name}/topics/{topic_name}/attachments",
            status_code=302,
        )
    except Exception as e:
        try:
            attachments = await att_svc.list_attachments(db, web_name, topic_name)
        except Exception:
            attachments = []
        ctx = PageContext(
            title=f"Attachments — {web_name}.{topic_name}",
            user=user, web=web_name, topic=topic_name,
        )
        return templates.TemplateResponse("topics/attachments.html", {
            **ctx.to_dict(request),
            "web": web_name,
            "topic_name": topic_name,
            "attachments": attachments,
            "fmt_size": _fmt_size,
            "error": str(e),
            "success": "",
        }, status_code=400)


# ── Download ──────────────────────────────────────────────────────────────────

@router.get("/webs/{web_name}/topics/{topic_name}/attachments/{filename}")
async def download_attachment(
    web_name: str,
    topic_name: str,
    filename: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    attachment, full_path = await att_svc.get_attachment(db, web_name, topic_name, filename)
    return FileResponse(
        path=str(full_path),
        filename=attachment.filename,
        media_type=attachment.content_type,
    )


# ── Update comment ───────────────────────────────────────────────────────────

@router.post("/webs/{web_name}/topics/{topic_name}/attachments/{filename}/comment")
async def update_attachment_comment(
    web_name: str,
    topic_name: str,
    filename: str,
    request: Request,
    comment: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    await att_svc.update_comment(db, web_name, topic_name, filename, comment)
    return RedirectResponse(
        url=f"/webs/{web_name}/topics/{topic_name}/attachments",
        status_code=302,
    )


# ── Delete ────────────────────────────────────────────────────────────────────

@router.post("/webs/{web_name}/topics/{topic_name}/attachments/{filename}/delete")
async def delete_attachment(
    web_name: str,
    topic_name: str,
    filename: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    await att_svc.delete_attachment(db, web_name, topic_name, filename)
    return RedirectResponse(
        url=f"/webs/{web_name}/topics/{topic_name}/attachments",
        status_code=302,
    )
