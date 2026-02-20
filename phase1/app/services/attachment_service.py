#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Attachment service
==================
Handles file upload to disk, metadata persistence, and download streaming.
Files are stored under:  {upload_dir}/{web_name}/{topic_name}/{filename}
"""

from __future__ import annotations

import mimetypes
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.attachment import Attachment
from app.models.user import User
from app.schemas import AttachmentOut
from app.services.topic_service import _get_topic

settings = get_settings()

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._\-]")
_MAX_BYTES = settings.max_upload_size_mb * 1024 * 1024


def _safe_name(filename: str) -> str:
    """Sanitise a filename: keep extension, replace dangerous chars."""
    name = Path(filename).stem
    ext = Path(filename).suffix
    safe = _SAFE_FILENAME.sub("_", name)
    return f"{safe}{ext}" if safe else f"upload{ext}"


def _storage_path(web: str, topic: str, filename: str) -> Path:
    base = Path(settings.upload_dir)
    return base / web / topic / filename


async def list_attachments(
    db: AsyncSession, web_name: str, topic_name: str, base_url: str
) -> list[AttachmentOut]:
    topic = await _get_topic(db, web_name, topic_name)
    result = await db.execute(
        select(Attachment, User.username)
        .outerjoin(User, User.id == Attachment.uploaded_by_id)
        .where(Attachment.topic_id == topic.id)
        .order_by(Attachment.uploaded_at)
    )
    out = []
    for att, username in result.all():
        out.append(_to_out(att, username, web_name, topic_name, base_url))
    return out


async def upload_attachment(
    db: AsyncSession,
    web_name: str,
    topic_name: str,
    file: UploadFile,
    comment: str = "",
    author_id: Optional[uuid.UUID] = None,
    base_url: str = "",
) -> AttachmentOut:
    topic = await _get_topic(db, web_name, topic_name)

    original = file.filename or "upload.bin"
    safe = _safe_name(original)
    storage = _storage_path(web_name, topic_name, safe)
    storage.parent.mkdir(parents=True, exist_ok=True)

    # Stream to disk with size check
    total_bytes = 0
    async with aiofiles.open(storage, "wb") as out:
        while chunk := await file.read(65536):
            total_bytes += len(chunk)
            if total_bytes > _MAX_BYTES:
                storage.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
                )
            await out.write(chunk)

    content_type = (
        file.content_type
        or mimetypes.guess_type(original)[0]
        or "application/octet-stream"
    )

    att = Attachment(
        topic_id=topic.id,
        filename=safe,
        original_filename=original,
        content_type=content_type,
        size_bytes=total_bytes,
        storage_path=str(storage),
        comment=comment,
        uploaded_by_id=author_id,
    )
    db.add(att)
    await db.flush()
    await db.refresh(att)

    uploader: Optional[str] = None
    if author_id:
        res = await db.execute(select(User).where(User.id == author_id))
        u = res.scalar_one_or_none()
        if u:
            uploader = u.username

    return _to_out(att, uploader, web_name, topic_name, base_url)


async def get_attachment_path(
    db: AsyncSession, web_name: str, topic_name: str, filename: str
) -> tuple[Path, str]:
    """Returns (path_on_disk, content_type) for streaming."""
    topic = await _get_topic(db, web_name, topic_name)
    result = await db.execute(
        select(Attachment).where(
            Attachment.topic_id == topic.id,
            Attachment.filename == filename,
        )
    )
    att = result.scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail=f"Attachment '{filename}' not found")
    path = Path(att.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return path, att.content_type


async def delete_attachment(
    db: AsyncSession, web_name: str, topic_name: str, filename: str
) -> None:
    topic = await _get_topic(db, web_name, topic_name)
    result = await db.execute(
        select(Attachment).where(
            Attachment.topic_id == topic.id,
            Attachment.filename == filename,
        )
    )
    att = result.scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail=f"Attachment '{filename}' not found")
    path = Path(att.storage_path)
    path.unlink(missing_ok=True)
    await db.delete(att)
    await db.flush()


def _to_out(att: Attachment, username: Optional[str], web: str, topic: str, base_url: str) -> AttachmentOut:
    return AttachmentOut(
        id=att.id,
        topic_id=att.topic_id,
        filename=att.filename,
        original_filename=att.original_filename,
        content_type=att.content_type,
        size_bytes=att.size_bytes,
        comment=att.comment,
        uploaded_by=username,
        uploaded_at=att.uploaded_at,
        download_url=f"{base_url}/api/v1/webs/{web}/topics/{topic}/attachments/{att.filename}",
    )



