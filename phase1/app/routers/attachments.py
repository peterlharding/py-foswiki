#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Attachments router
==================
GET    /api/v1/webs/{web}/topics/{topic}/attachments            — list attachments
POST   /api/v1/webs/{web}/topics/{topic}/attachments            — upload file
GET    /api/v1/webs/{web}/topics/{topic}/attachments/{filename} — download file
DELETE /api/v1/webs/{web}/topics/{topic}/attachments/{filename} — delete file
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_active_user
from app.models.user import User
from app.schemas import AttachmentOut
from app.services.attachment_service import (
    delete_attachment,
    get_attachment_path,
    list_attachments,
    upload_attachment,
)

settings = get_settings()
router = APIRouter(prefix="/webs/{web_name}/topics/{topic_name}/attachments", tags=["Attachments"])


@router.get("", response_model=list[AttachmentOut])
async def list_attachments_endpoint(
    web_name: str,
    topic_name: str,
    db: AsyncSession = Depends(get_db),
):
    return await list_attachments(db, web_name, topic_name, base_url=settings.base_url)


@router.post("", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment_endpoint(
    web_name: str,
    topic_name: str,
    file: UploadFile = File(...),
    comment: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return await upload_attachment(
        db,
        web_name,
        topic_name,
        file=file,
        comment=comment,
        author_id=current_user.id,
        base_url=settings.base_url,
    )


@router.get("/{filename}")
async def download_attachment_endpoint(
    web_name: str,
    topic_name: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
):
    path, content_type = await get_attachment_path(db, web_name, topic_name, filename)
    return FileResponse(
        path=str(path),
        media_type=content_type,
        filename=filename,
    )


@router.delete("/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment_endpoint(
    web_name: str,
    topic_name: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    await delete_attachment(db, web_name, topic_name, filename)




