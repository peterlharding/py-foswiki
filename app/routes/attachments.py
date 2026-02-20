#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Attachments router
==================
GET    /api/v1/webs/{web}/topics/{topic}/attachments           — list
POST   /api/v1/webs/{web}/topics/{topic}/attachments           — upload  [auth]
GET    /api/v1/webs/{web}/topics/{topic}/attachments/{file}    — download
DELETE /api/v1/webs/{web}/topics/{topic}/attachments/{file}    — delete  [auth]
"""
# -----------------------------------------------------------------------------


from __future__ import annotations

from fastapi import APIRouter, Depends, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.schemas import AttachmentResponse, OKResponse
from app.services import attachments as att_svc


# -----------------------------------------------------------------------------

router = APIRouter(
    prefix="/webs/{web_name}/topics/{topic_name}/attachments",
    tags=["attachments"],
)


# -----------------------------------------------------------------------------

@router.get("", response_model=list[AttachmentResponse])
async def list_attachments(
    web_name: str,
    topic_name: str,
    db: AsyncSession = Depends(get_db),
):
    attachments = await att_svc.list_attachments(db, web_name, topic_name)
    settings = get_settings()
    return [_att_response(a, settings.base_url) for a in attachments]


# -----------------------------------------------------------------------------

@router.post("", response_model=AttachmentResponse, status_code=201)
async def upload_attachment(
    web_name: str,
    topic_name: str,
    file: UploadFile,
    comment: str = Form(default=""),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    attachment = await att_svc.upload_attachment(
        db, web_name, topic_name, file, comment=comment, author_id=user_id
    )
    settings = get_settings()
    return _att_response(attachment, settings.base_url)


# -----------------------------------------------------------------------------

@router.get("/{filename}")
async def download_attachment(
    web_name: str,
    topic_name: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
):
    attachment, full_path = await att_svc.get_attachment(db, web_name, topic_name, filename)
    return FileResponse(
        path=str(full_path),
        filename=attachment.filename,
        media_type=attachment.content_type,
    )


# -----------------------------------------------------------------------------

@router.delete("/{filename}", response_model=OKResponse)
async def delete_attachment(
    web_name: str,
    topic_name: str,
    filename: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await att_svc.delete_attachment(db, web_name, topic_name, filename)
    return OKResponse(message=f"Attachment '{filename}' deleted")


# -----------------------------------------------------------------------------

def _att_response(a, base_url: str) -> dict:
    url = f"{base_url}/api/v1/webs/{{}}/topics/{{}}/attachments/{a.filename}"
    # We need web+topic name here; store in storage_path: web/topic/file
    parts = a.storage_path.split("/", 2)
    if len(parts) == 3:
        url = f"{base_url}/api/v1/webs/{parts[0]}/topics/{parts[1]}/attachments/{parts[2]}"
    return {
        "id":           a.id,
        "topic_id":     a.topic_id,
        "filename":     a.filename,
        "content_type": a.content_type,
        "size_bytes":   a.size_bytes,
        "comment":      a.comment,
        "uploaded_by":  a.uploaded_by,
        "uploaded_at":  a.uploaded_at,
        "url":          url,
    }


# -----------------------------------------------------------------------------

